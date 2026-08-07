"""Local FastAPI application for the browser measurement workbench."""

from __future__ import annotations

import mimetypes
import tomllib
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
import numpy.typing as npt
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from picmeasure.ball.detector import BallDetector
from picmeasure.ball.models import BallCandidate
from picmeasure.config import AppConfig, PrecisionConfig, StereoConfig
from picmeasure.precision import snap_to_centerline, snap_to_edge
from picmeasure.stereo.board_calibration import (
    calibrate_stereo_board,
    stereo_config_to_toml,
)
from picmeasure.stereo.calibration import (
    RectificationMaps,
    build_rectification,
    calibration_from_config,
    rectify_image,
)
from picmeasure.stereo.correspondence import match_along_epipolar_line
from picmeasure.stereo.geometry import triangulate_rectified

ImageArray = npt.NDArray[np.uint8]
Point = tuple[int, int]


@dataclass
class WebSession:
    """In-memory images and calibration for one browser tab."""

    mode: Literal["monocular", "stereo"]
    primary: ImageArray
    right: ImageArray | None = None
    stereo_config: StereoConfig | None = None
    rectification: RectificationMaps | None = None


class PointPayload(BaseModel):  # type: ignore[misc]
    """One browser-space image point request."""

    session_id: str
    point: Point
    mode: Literal["length", "diameter"]
    previous: Point | None = None
    snapping: bool = True


class StereoPointPayload(PointPayload):
    """A left-image point that also requires right correspondence."""

    manual_right: Point | None = None


SESSIONS: dict[str, WebSession] = {}
STATIC_DIR = Path(__file__).with_name("web_static")

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/json", ".json")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("application/wasm", ".wasm")

app = FastAPI(title="PicMeasure", docs_url="/api/docs", redoc_url=None)


def _decode_image(data: bytes) -> ImageArray:
    encoded = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="无法读取图像文件")
    return image


async def _read_image(upload: UploadFile) -> ImageArray:
    return _decode_image(await upload.read())


def _session(session_id: str) -> WebSession:
    session = SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="测量会话不存在或服务已重启")
    return session


def _candidate_dict(candidate: BallCandidate, physical_diameter: float) -> dict[str, object]:
    return {
        "center": list(candidate.center_xy),
        "radius": candidate.radius_px,
        "score": candidate.score,
        "mask_fill": candidate.mask_fill,
        "circularity": candidate.circularity,
        "edge_support": candidate.edge_support,
        "area_ratio": candidate.area_ratio,
        "method": candidate.method,
        "pixels_per_unit": 2.0 * candidate.radius_px / physical_diameter,
    }


def _image_meta(image: ImageArray) -> dict[str, int]:
    return {"width": int(image.shape[1]), "height": int(image.shape[0])}


@app.post("/api/calibration/stereo")
async def calibrate_stereo(
    left_images: list[UploadFile] = File(...),
    right_images: list[UploadFile] = File(...),
    columns: int = Form(...),
    rows: int = Form(...),
    square_size: float = Form(...),
    unit: Literal["mm", "cm"] = Form("mm"),
    baseline: float | None = Form(None),
) -> dict[str, object]:
    """Calibrate a stereo rig from synchronized chessboard image pairs."""
    if len(left_images) != len(right_images):
        raise HTTPException(status_code=400, detail="左右标定图数量必须一致")
    try:
        decoded_left = [await _read_image(upload) for upload in left_images]
        decoded_right = [await _read_image(upload) for upload in right_images]
        result = calibrate_stereo_board(
            decoded_left,
            decoded_right,
            columns=columns,
            rows=rows,
            square_size=square_size,
            unit=unit,
            known_baseline=baseline,
        )
    except (ValueError, cv2.error) as exc:
        raise HTTPException(status_code=400, detail=f"双目标定失败：{exc}") from exc

    config = result.config
    assert config.left is not None
    assert config.right is not None
    assert config.quality is not None
    return {
        "toml": stereo_config_to_toml(config),
        "accepted_indices": result.accepted_indices,
        "rejected_indices": result.rejected_indices,
        "image_size": list(config.image_size or ()),
        "unit": config.unit,
        "baseline": config.baseline_units,
        "rotation": config.rotation,
        "translation": config.translation,
        "left": config.left.model_dump(),
        "right": config.right.model_dump(),
        "quality": config.quality.model_dump(),
    }


@app.post("/api/sessions/monocular")
async def create_monocular_session(image: UploadFile = File(...)) -> dict[str, object]:
    """Create a session from one image and return ranked ball candidates."""
    decoded = await _read_image(image)
    session_id = uuid.uuid4().hex
    SESSIONS[session_id] = WebSession(mode="monocular", primary=decoded)
    config = AppConfig()
    candidates = BallDetector(config.ball).detect_candidates(decoded)
    return {
        "session_id": session_id,
        "mode": "monocular",
        "images": {"primary": _image_meta(decoded)},
        "ball_candidates": [
            _candidate_dict(candidate, config.ball.known_diameter_cm) for candidate in candidates
        ],
        "known_ball_diameter": config.ball.known_diameter_cm,
        "unit": config.output_unit,
    }


@app.post("/api/sessions/stereo")
async def create_stereo_session(
    left: UploadFile = File(...),
    right: UploadFile = File(...),
) -> dict[str, object]:
    """Create and rectify a stereo pair using the project-root calibration."""
    left_image = await _read_image(left)
    right_image = await _read_image(right)
    if left_image.shape[:2] != right_image.shape[:2]:
        raise HTTPException(status_code=400, detail="左右图尺寸必须一致")
    # In a packaged app the user-editable calibration lives beside the launcher;
    # during development fall back to the repository root.
    candidates = [Path.cwd() / "stereo.toml", Path(__file__).resolve().parents[2] / "stereo.toml"]
    calibration_path = next((path for path in candidates if path.is_file()), candidates[0])
    if not calibration_path.is_file():
        raise HTTPException(
            status_code=400,
            detail=f"找不到根目录标定文件：{calibration_path.name}，请先生成并放置 stereo.toml",
        )
    try:
        raw_config = tomllib.loads(calibration_path.read_text(encoding="utf-8"))
        stereo_config = StereoConfig(**raw_config.get("stereo", raw_config))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"双目标定配置无效：{exc}") from exc
    stereo_config.enabled = True
    height, width = left_image.shape[:2]
    if stereo_config.image_size is not None and stereo_config.image_size != (width, height):
        expected_width, expected_height = stereo_config.image_size
        raise HTTPException(
            status_code=400,
            detail=(
                f"图像尺寸为 {width}x{height}，标定文件要求 "
                f"{expected_width}x{expected_height}；请使用标定时的分辨率"
            ),
        )
    normalized = calibration_from_config(stereo_config, (width, height))
    try:
        maps = build_rectification(normalized)
    except cv2.error as exc:
        raise HTTPException(status_code=400, detail=f"双目标定无法校正图像：{exc}") from exc
    rect_left = rectify_image(left_image, maps.map1x, maps.map1y)
    rect_right = rectify_image(right_image, maps.map2x, maps.map2y)
    session_id = uuid.uuid4().hex
    SESSIONS[session_id] = WebSession(
        mode="stereo",
        primary=rect_left,
        right=rect_right,
        stereo_config=stereo_config,
        rectification=maps,
    )
    ball_config = AppConfig().ball
    detector = BallDetector(ball_config)
    return {
        "session_id": session_id,
        "mode": "stereo",
        "images": {"left": _image_meta(rect_left), "right": _image_meta(rect_right)},
        "ball_candidates": {
            "left": [
                _candidate_dict(candidate, ball_config.known_diameter_cm)
                for candidate in detector.detect_candidates(rect_left)
            ],
            "right": [
                _candidate_dict(candidate, ball_config.known_diameter_cm)
                for candidate in detector.detect_candidates(rect_right)
            ],
        },
        "known_ball_diameter": ball_config.known_diameter_cm,
        "unit": stereo_config.unit,
    }


@app.get("/api/sessions/{session_id}/images/{view}")
def session_image(session_id: str, view: Literal["primary", "left", "right"]) -> Response:
    """Return a session image without creating persistent upload files."""
    session = _session(session_id)
    image = session.right if view == "right" else session.primary
    if image is None:
        raise HTTPException(status_code=404, detail="该会话没有右图")
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not ok:
        raise HTTPException(status_code=500, detail="图像编码失败")
    return Response(encoded.tobytes(), media_type="image/jpeg")


def _snap(image: ImageArray, payload: PointPayload) -> dict[str, object]:
    raw = tuple(payload.point)
    if not payload.snapping:
        return {"raw": list(raw), "candidate": list(raw), "snapped": False, "score": 0.0}
    precision = PrecisionConfig()
    preview = (
        snap_to_edge(image, raw, precision)
        if payload.mode == "diameter"
        else snap_to_centerline(image, raw, payload.previous, precision)
    )
    return {
        "raw": list(preview.raw),
        "candidate": list(preview.candidate),
        "snapped": preview.snapped,
        "score": preview.score,
    }


@app.post("/api/points/snap")
def snap_point(payload: PointPayload) -> dict[str, object]:
    """Return an edge- or centerline-assisted preview for a monocular point."""
    session = _session(payload.session_id)
    return _snap(session.primary, payload)


@app.post("/api/points/stereo")
def stereo_point(payload: StereoPointPayload) -> dict[str, object]:
    """Snap a left point, match the right image, and triangulate the pair."""
    session = _session(payload.session_id)
    if (
        session.mode != "stereo"
        or session.right is None
        or session.stereo_config is None
        or session.rectification is None
    ):
        raise HTTPException(status_code=400, detail="当前会话不是有效双目会话")
    preview = _snap(session.primary, payload)
    left_point = tuple(preview["candidate"])
    try:
        if payload.manual_right is None:
            match = match_along_epipolar_line(
                session.primary,
                session.right,
                left_point,
                session.stereo_config.correspondence,
            )
            right_point = (int(round(match.right_pt[0])), int(round(match.right_pt[1])))
            match_score = match.score
            manual = False
        else:
            right_point = tuple(payload.manual_right)
            match_score = 1.0
            manual = True
        point_3d = triangulate_rectified(
            left_point,
            right_point,
            session.rectification.p1,
            session.rectification.p2,
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    preview.update(
        {
            "right": list(right_point),
            "point_3d": [point_3d.x, point_3d.y, point_3d.z],
            "match_score": match_score,
            "manual": manual,
        }
    )
    return preview


@app.delete("/api/sessions/{session_id}", status_code=204)
def delete_session(session_id: str) -> Response:
    """Release images when a browser starts another session."""
    SESSIONS.pop(session_id, None)
    return Response(status_code=204)


if STATIC_DIR.exists():
    assets = STATIC_DIR / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}")
    def web_app(path: str) -> FileResponse:
        """Serve the single-page workbench and its browser routes."""
        candidate = STATIC_DIR / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")
