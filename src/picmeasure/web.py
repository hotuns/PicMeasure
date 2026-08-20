"""Local FastAPI application for the browser measurement workbench."""

from __future__ import annotations

import mimetypes
import json
import re
import io
import tomllib
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

import cv2
import numpy as np
import numpy.typing as npt
import pymysql
from openpyxl import Workbook
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from picmeasure.ball.detector import BallDetector
from picmeasure.ball.models import BallCandidate
from picmeasure.config import AppConfig, PrecisionConfig, StereoConfig
from picmeasure.precision import snap_to_centerline, snap_to_edge
from picmeasure.remote_data import download_remote_image, list_capture_groups
from picmeasure.stereo.board_calibration import (
    calibrate_stereo_board,
    stereo_config_to_toml,
)
from picmeasure.stereo.calibration import (
    RectificationMaps,
    calibration_from_config,
    rectify_image,
)
from picmeasure.stereo.correspondence import match_along_epipolar_line
from picmeasure.stereo.geometry import triangulate_rectified
from picmeasure.stereo.online_pose import refine_rectification

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
    source: dict[str, object] | None = None


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


class AnnotationPayload(BaseModel):  # type: ignore[misc]
    """One locally persisted image annotation result."""

    session_id: str
    captured_at: str | None = None
    branches: list[dict[str, Any]]
    calibration: dict[str, Any] = {}


SESSIONS: dict[str, WebSession] = {}
STATIC_DIR = Path(__file__).with_name("web_static")
LOCAL_DATA_DIR = Path.cwd() / "data"

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


def _create_monocular_from_image(
    image: ImageArray, source: dict[str, object] | None = None
) -> dict[str, object]:
    session_id = uuid.uuid4().hex
    SESSIONS[session_id] = WebSession(mode="monocular", primary=image, source=source)
    config = AppConfig()
    candidates = BallDetector(config.ball).detect_candidates(image)
    saved_calibration = _saved_monocular_calibration(source)
    return {
        "session_id": session_id,
        "mode": "monocular",
        "images": {"primary": _image_meta(image)},
        "ball_candidates": [
            _candidate_dict(candidate, config.ball.known_diameter_cm)
            for candidate in candidates
        ],
        "known_ball_diameter": config.ball.known_diameter_cm,
        "unit": config.output_unit,
        "source": source,
        "saved_calibration": saved_calibration,
    }


def _saved_monocular_calibration(
    source: dict[str, object] | None,
) -> dict[str, object] | None:
    """Load a reusable scale profile for one fixed remote camera key."""
    if not source or source.get("kind") != "remote":
        return None
    image = source.get("image")
    if not isinstance(image, dict) or not image.get("key"):
        return None
    device_id = source.get("device_id")
    path = LOCAL_DATA_DIR / "calibrations" / str(device_id) / f"{image['key']}.json"
    if not path.is_file():
        annotation_root = LOCAL_DATA_DIR / "annotations" / str(device_id)
        for annotation_path in sorted(
            annotation_root.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True
        ) if annotation_root.is_dir() else []:
            try:
                record = json.loads(annotation_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            record_source = record.get("source", {})
            record_image = record_source.get("image")
            primary = record.get("calibration", {}).get("primary")
            if isinstance(record_image, dict) and record_image.get("key") == image["key"] and isinstance(primary, dict):
                return {
                    **primary,
                    "device_id": device_id,
                    "image_key": image["key"],
                    "saved_at": record.get("saved_at"),
                }
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _save_monocular_calibration(
    source: dict[str, object], calibration: dict[str, Any]
) -> None:
    """Persist the confirmed reference-ball scale for a fixed camera key."""
    image = source.get("image")
    primary = calibration.get("primary")
    if not isinstance(image, dict) or not image.get("key") or not isinstance(primary, dict):
        return
    device_id = source.get("device_id")
    target_dir = LOCAL_DATA_DIR / "calibrations" / str(device_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    profile = {
        **primary,
        "device_id": device_id,
        "image_key": image["key"],
        "saved_at": datetime.now().isoformat(timespec="seconds"),
    }
    (target_dir / f"{image['key']}.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _load_stereo_config(size: tuple[int, int], calibration_toml: bytes | None = None) -> StereoConfig:
    candidates = [Path.cwd() / "stereo.toml", Path(__file__).resolve().parents[2] / "stereo.toml"]
    calibration_path = next((path for path in candidates if path.is_file()), candidates[0])
    if calibration_toml is None and not calibration_path.is_file():
        raise HTTPException(status_code=400, detail="找不到根目录标定文件 stereo.toml")
    try:
        config_text = (
            calibration_toml.decode("utf-8")
            if calibration_toml is not None
            else calibration_path.read_text(encoding="utf-8")
        )
        raw_config = tomllib.loads(config_text)
        stereo_config = StereoConfig(**raw_config.get("stereo", raw_config))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"双目标定配置无效：{exc}") from exc
    stereo_config.enabled = True
    if stereo_config.image_size is not None and stereo_config.image_size != size:
        raise HTTPException(
            status_code=400,
            detail=(
                f"图像尺寸为 {size[0]}x{size[1]}，标定文件要求 "
                f"{stereo_config.image_size[0]}x{stereo_config.image_size[1]}"
            ),
        )
    return stereo_config


def _create_stereo_from_images(
    left_image: ImageArray,
    right_image: ImageArray,
    source: dict[str, object] | None = None,
    calibration_toml: bytes | None = None,
) -> dict[str, object]:
    if left_image.shape[:2] != right_image.shape[:2]:
        raise HTTPException(status_code=400, detail="左右图尺寸必须一致")
    height, width = left_image.shape[:2]
    stereo_config = _load_stereo_config((width, height), calibration_toml)
    normalized = calibration_from_config(stereo_config, (width, height))
    try:
        alignment = refine_rectification(left_image, right_image, normalized)
        maps = alignment.maps
    except (cv2.error, ValueError) as exc:
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
        source=source,
    )
    ball_config = AppConfig().ball
    detector = BallDetector(ball_config)
    return {
        "session_id": session_id,
        "mode": "stereo",
        "images": {"left": _image_meta(rect_left), "right": _image_meta(rect_right)},
        "ball_candidates": {
            "left": [_candidate_dict(c, ball_config.known_diameter_cm) for c in detector.detect_candidates(rect_left)],
            "right": [_candidate_dict(c, ball_config.known_diameter_cm) for c in detector.detect_candidates(rect_right)],
        },
        "known_ball_diameter": ball_config.known_diameter_cm,
        "unit": stereo_config.unit,
        "source": source,
        "alignment": {
            "source": alignment.source,
            "matches": alignment.match_count,
            "inliers": alignment.inlier_count,
            "median_vertical_error_px": alignment.median_vertical_error_px,
            "p90_vertical_error_px": alignment.p90_vertical_error_px,
        },
    }


def _source_target(source: dict[str, object]) -> str:
    """Return the independently measurable target within a capture round."""
    image = source.get("image")
    if isinstance(image, dict) and image.get("key"):
        return str(image["key"])
    if source.get("left") and source.get("right"):
        return "stereo-key3-key2"
    return "local"


def _existing_branches(source: dict[str, object]) -> list[dict[str, Any]]:
    """Load the saved branches for an exact remote capture and image target."""
    device_id = str(source.get("device_id", "local"))
    capture_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(source.get("capture_id", "")))
    target = re.sub(r"[^A-Za-z0-9_.-]+", "_", _source_target(source))
    path = LOCAL_DATA_DIR / "annotations" / device_id / f"{capture_id}__{target}.json"
    if not path.is_file():
        return []
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    branches = record.get("branches", [])
    return branches if isinstance(branches, list) else []


def _measurement_status(device_id: int) -> dict[tuple[str, str], dict[str, object]]:
    root = LOCAL_DATA_DIR / "annotations" / str(device_id)
    status: dict[tuple[str, str], dict[str, object]] = {}
    if not root.is_dir():
        return status
    for path in root.glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        source = record.get("source", {})
        capture_id = str(source.get("capture_id", ""))
        if not capture_id:
            continue
        target = _source_target(source)
        status[(capture_id, target)] = {
            "measured": True,
            "saved_at": record.get("saved_at"),
            "branch_count": len(record.get("branches", [])),
            "path": str(path),
        }
    return status


def _annotation_paths(session: WebSession) -> tuple[Path, str, str]:
    source = session.source or {"kind": "local"}
    device_id = str(source.get("device_id", "local"))
    capture_id = str(source.get("capture_id", "local"))
    safe_capture = re.sub(r"[^A-Za-z0-9_.-]+", "_", capture_id)
    safe_target = re.sub(r"[^A-Za-z0-9_.-]+", "_", _source_target(source))
    return LOCAL_DATA_DIR / "annotations" / device_id, safe_capture, safe_target


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
    return _create_monocular_from_image(decoded)


@app.post("/api/sessions/stereo")
async def create_stereo_session(
    left: UploadFile = File(...),
    right: UploadFile = File(...),
    calibration: UploadFile | None = File(None),
) -> dict[str, object]:
    """Create and rectify a stereo pair using the project-root calibration."""
    left_image = await _read_image(left)
    right_image = await _read_image(right)
    calibration_toml = await calibration.read() if calibration is not None else None
    return _create_stereo_from_images(left_image, right_image, calibration_toml=calibration_toml)


@app.get("/api/remote/devices/{device_id}/captures")
def remote_captures(
    device_id: int,
    limit: int = 30,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """List recent OSS image rounds for a THCPN device."""
    try:
        result = list_capture_groups(
            device_id,
            max(1, min(limit, 100)),
            start_date=start_date,
            end_date=end_date,
        )
        status = _measurement_status(device_id)
        for capture in result["captures"]:
            capture_id = capture["id"]
            for key, image in capture["images"].items():
                image["measurement"] = status.get(
                    (capture_id, key), {"measured": False}
                )
            capture["stereo_measurement"] = status.get(
                (capture_id, "stereo-key3-key2"), {"measured": False}
            )
        return result
    except (RuntimeError, ValueError, OSError, pymysql.MySQLError) as exc:
        raise HTTPException(status_code=502, detail=f"读取远程设备失败：{exc}") from exc


@app.get("/api/remote/devices/{device_id}/image")
def remote_image(device_id: int, path: str) -> Response:
    """Proxy an OSS image through the local service."""
    try:
        data = download_remote_image(device_id, path)
    except (RuntimeError, ValueError, OSError) as exc:
        raise HTTPException(status_code=502, detail=f"下载 OSS 图片失败：{exc}") from exc
    suffix = Path(path).suffix.lower()
    media_type = "image/png" if suffix == ".png" else "image/jpeg"
    return Response(data, media_type=media_type, headers={"Cache-Control": "private, max-age=3600"})


@app.post("/api/sessions/remote-stereo")
async def create_remote_stereo_session(
    device_id: int = Form(3331),
    capture_id: str = Form(...),
    captured_at: str = Form(...),
    left_path: str = Form(...),
    right_path: str = Form(...),
    calibration: UploadFile | None = File(None),
) -> dict[str, object]:
    """Download key3 as left and key2 as right, then create a stereo session."""
    try:
        left_image = _decode_image(download_remote_image(device_id, left_path))
        right_image = _decode_image(download_remote_image(device_id, right_path))
    except (RuntimeError, ValueError, OSError) as exc:
        raise HTTPException(status_code=502, detail=f"下载远程双目图片失败：{exc}") from exc
    source: dict[str, object] = {
        "kind": "remote",
        "device_id": device_id,
        "capture_id": capture_id,
        "captured_at": captured_at,
        "left": {"key": "key3", "path": left_path},
        "right": {"key": "key2", "path": right_path},
        "calibration": calibration.filename if calibration is not None else "stereo.toml",
    }
    calibration_toml = await calibration.read() if calibration is not None else None
    return _create_stereo_from_images(
        left_image, right_image, source, calibration_toml=calibration_toml
    )


@app.post("/api/sessions/remote-monocular")
def create_remote_monocular_session(
    device_id: int = Form(3331),
    capture_id: str = Form(...),
    captured_at: str = Form(...),
    image_key: str = Form(...),
    image_path: str = Form(...),
) -> dict[str, object]:
    """Download one remote image and create a monocular measuring session."""
    try:
        image = _decode_image(download_remote_image(device_id, image_path))
    except (RuntimeError, ValueError, OSError) as exc:
        raise HTTPException(status_code=502, detail=f"下载远程单目图片失败：{exc}") from exc
    source: dict[str, object] = {
        "kind": "remote",
        "device_id": device_id,
        "capture_id": capture_id,
        "captured_at": captured_at,
        "image": {"key": image_key, "path": image_path},
    }
    response = _create_monocular_from_image(image, source)
    response["existing_branches"] = _existing_branches(source)
    return response


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


@app.post("/api/annotations")
def save_annotation(payload: AnnotationPayload) -> dict[str, object]:
    """Persist the current semantic measurements as a local JSON record."""
    session = _session(payload.session_id)
    source = session.source or {"kind": "local"}
    device_id = source.get("device_id", "local")
    capture_id = str(source.get("capture_id", payload.session_id))
    target_id = _source_target(source)
    captured_at = payload.captured_at or str(source.get("captured_at", datetime.now().isoformat()))
    record = {
        "schema_version": 2,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "captured_at": captured_at,
        "mode": session.mode,
        "unit": session.stereo_config.unit if session.stereo_config else AppConfig().output_unit,
        "source": source,
        "calibration": payload.calibration,
        "branches": payload.branches,
    }
    target_dir, safe_capture, safe_target = _annotation_paths(session)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{safe_capture}__{safe_target}.json"
    target.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    if session.mode == "monocular" and source.get("kind") == "remote":
        _save_monocular_calibration(source, payload.calibration)
    return {"saved": True, "path": str(target), "captured_at": captured_at}


@app.post("/api/annotations/{session_id}/image")
async def save_annotation_image(
    session_id: str, image: UploadFile = File(...)
) -> dict[str, object]:
    """Persist the rendered measurement image beside its JSON result."""
    session = _session(session_id)
    target_dir, safe_capture, safe_target = _annotation_paths(session)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{safe_capture}__{safe_target}.png"
    target.write_bytes(await image.read())
    return {"saved": True, "path": str(target)}


@app.get("/api/exports/device/{device_id}")
def export_device_measurements(device_id: int) -> Response:
    """Export local measurements as an Excel workbook plus annotated images."""
    root = LOCAL_DATA_DIR / "annotations" / str(device_id)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "测量结果"
    sheet.append(
        [
            "采集时间",
            "图片目标",
            "业务key",
            "长度",
            "单位",
            "直径序号",
            "直径",
            "保存时间",
            "源图片",
        ]
    )
    records: list[tuple[Path, dict[str, Any]]] = []
    if root.is_dir():
        for path in sorted(root.glob("*.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            records.append((path, record))
            source = record.get("source", {})
            target = _source_target(source)
            source_image = source.get("image", source.get("left", {})).get("path", "")
            for branch in record.get("branches", []):
                diameters = branch.get("diameter_measurements", branch.get("diameters", []))
                if diameters:
                    for diameter in diameters:
                        sheet.append(
                            [
                                record.get("captured_at"), target, branch.get("key"),
                                branch.get("length_units"), branch.get("unit", record.get("unit")),
                                diameter.get("sectionId"), diameter.get("value"),
                                record.get("saved_at"), source_image,
                            ]
                        )
                else:
                    sheet.append(
                        [
                            record.get("captured_at"), target, branch.get("key"),
                            branch.get("length_units"), branch.get("unit", record.get("unit")),
                            None, None, record.get("saved_at"), source_image,
                        ]
                    )
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    widths = [20, 20, 18, 14, 10, 12, 14, 20, 48]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[chr(64 + index)].width = width
    excel = io.BytesIO()
    workbook.save(excel)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("measurements.xlsx", excel.getvalue())
        for json_path, _ in records:
            image_path = json_path.with_suffix(".png")
            if image_path.is_file():
                bundle.write(image_path, f"annotated_images/{image_path.name}")
    filename = f"picmeasure-device-{device_id}.zip"
    return Response(
        archive.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/annotations/series")
def annotation_series(device_id: int = 3331) -> dict[str, object]:
    """Build chronological length series grouped by semantic key."""
    root = LOCAL_DATA_DIR / "annotations" / str(device_id)
    series: dict[str, list[dict[str, object]]] = {}
    if root.is_dir():
        for path in root.glob("*.json"):
            record = json.loads(path.read_text(encoding="utf-8"))
            for branch in record.get("branches", []):
                key = str(branch.get("key", "")).strip()
                value = branch.get("length_units")
                if key and isinstance(value, int | float):
                    image_path = path.with_suffix(".png")
                    series.setdefault(key, []).append(
                        {
                            "timestamp": record.get("captured_at", record.get("saved_at")),
                            "value": float(value),
                            "unit": branch.get("unit", record.get("unit", "mm")),
                            "capture_id": record.get("source", {}).get("capture_id"),
                            "annotation_id": path.name,
                            "target": _source_target(record.get("source", {})),
                            "image_url": (
                                f"/api/annotations/device/{device_id}/image/"
                                f"{quote(image_path.name)}"
                                if image_path.is_file()
                                else None
                            ),
                        }
                    )
    for values in series.values():
        values.sort(key=lambda point: str(point["timestamp"]))
    return {"device_id": device_id, "series": series}


@app.post("/api/sessions/from-annotation/{device_id}/{filename}")
def create_session_from_annotation(device_id: int, filename: str) -> dict[str, object]:
    """Reopen the remote source image recorded by one saved annotation."""
    if Path(filename).name != filename or not filename.lower().endswith(".json"):
        raise HTTPException(status_code=404, detail="测量结果不存在")
    path = LOCAL_DATA_DIR / "annotations" / str(device_id) / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="测量结果不存在")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        source = record.get("source", {})
        if source.get("kind") != "remote":
            raise ValueError("该记录不是远程图片")
        image = source.get("image")
        if not isinstance(image, dict) or not image.get("path"):
            raise ValueError("该记录没有可重新打开的单目源图片")
        decoded = _decode_image(download_remote_image(device_id, str(image["path"])))
        response = _create_monocular_from_image(decoded, source)
        response["existing_branches"] = record.get("branches", [])
        return response
    except (OSError, json.JSONDecodeError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"无法重新打开测量图片：{exc}") from exc


@app.get("/api/annotations/device/{device_id}")
def list_device_annotations(device_id: int) -> dict[str, object]:
    """List locally saved measurement records for the table view."""
    root = LOCAL_DATA_DIR / "annotations" / str(device_id)
    records: list[dict[str, object]] = []
    if root.is_dir():
        for path in root.glob("*.json"):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            branches = record.get("branches", [])
            records.append(
                {
                    "id": path.name,
                    "captured_at": record.get("captured_at"),
                    "saved_at": record.get("saved_at"),
                    "mode": record.get("mode"),
                    "target": _source_target(record.get("source", {})),
                    "measurements": [
                        {
                            "key": branch.get("key"),
                            "value": branch.get("length_units"),
                            "unit": branch.get("unit", record.get("unit")),
                        }
                        for branch in branches
                    ],
                    "image_url": (
                        f"/api/annotations/device/{device_id}/image/{quote(path.with_suffix('.png').name)}"
                        if path.with_suffix(".png").is_file()
                        else None
                    ),
                }
            )
    records.sort(key=lambda item: str(item.get("captured_at", "")), reverse=True)
    return {"device_id": device_id, "records": records}


@app.delete("/api/annotations/device/{device_id}/{filename}", status_code=204)
def delete_device_annotation(device_id: int, filename: str) -> Response:
    """Delete one saved JSON result and its rendered annotation image."""
    if Path(filename).name != filename or not filename.lower().endswith(".json"):
        raise HTTPException(status_code=404, detail="测量结果不存在")
    root = LOCAL_DATA_DIR / "annotations" / str(device_id)
    target = root / filename
    if not target.is_file():
        raise HTTPException(status_code=404, detail="测量结果不存在")
    target.unlink()
    image = target.with_suffix(".png")
    if image.is_file():
        image.unlink()
    return Response(status_code=204)


@app.get("/api/annotations/device/{device_id}/image/{filename}")
def annotation_image(device_id: int, filename: str) -> FileResponse:
    """Serve one locally saved annotated measurement image."""
    if Path(filename).name != filename or not filename.lower().endswith(".png"):
        raise HTTPException(status_code=404, detail="标注图不存在")
    target = LOCAL_DATA_DIR / "annotations" / str(device_id) / filename
    if not target.is_file():
        raise HTTPException(status_code=404, detail="标注图不存在")
    return FileResponse(target, media_type="image/png")


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
