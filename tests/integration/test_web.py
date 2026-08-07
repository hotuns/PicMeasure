"""Integration tests for the local browser API."""

from __future__ import annotations

import io
from pathlib import Path

import cv2
import pytest
from fastapi.testclient import TestClient

from picmeasure.web import SESSIONS, app


@pytest.fixture(autouse=True)
def clear_web_sessions() -> None:
    SESSIONS.clear()


@pytest.fixture
def web_client() -> TestClient:
    return TestClient(app)


@pytest.mark.integration
def test_web_workbench_is_served(web_client: TestClient) -> None:
    response = web_client.get("/")
    assert response.status_code == 200
    assert "PicMeasure" in response.text


@pytest.mark.integration
def test_monocular_session_returns_image_and_ball_candidates(
    web_client: TestClient, synthetic_ball_image
) -> None:
    ok, encoded = cv2.imencode(".png", synthetic_ball_image)
    assert ok

    response = web_client.post(
        "/api/sessions/monocular",
        files={"image": ("ball.png", io.BytesIO(encoded.tobytes()), "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "monocular"
    assert body["images"]["primary"] == {"width": 800, "height": 600}
    assert body["ball_candidates"]
    image = web_client.get(f"/api/sessions/{body['session_id']}/images/primary")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/jpeg"


@pytest.mark.integration
def test_monocular_snap_endpoint_uses_existing_precision_algorithm(
    web_client: TestClient, synthetic_ball_image
) -> None:
    ok, encoded = cv2.imencode(".png", synthetic_ball_image)
    assert ok
    session = web_client.post(
        "/api/sessions/monocular",
        files={"image": ("image.png", encoded.tobytes(), "image/png")},
    ).json()

    response = web_client.post(
        "/api/points/snap",
        json={
            "session_id": session["session_id"],
            "point": [460, 300],
            "mode": "diameter",
            "snapping": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["snapped"] is True


@pytest.mark.integration
def test_stereo_session_supports_manual_correspondence(
    web_client: TestClient,
    synthetic_stereo_pair: tuple[Path, Path, float],
) -> None:
    left, right, _ = synthetic_stereo_pair
    calibration = b"""
[stereo]
enabled = true
focal_length_px = 800.0
principal_point = [320.0, 240.0]
distortion_coefficients = [0.0, 0.0, 0.0, 0.0, 0.0]
rotation = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
translation = [10.0, 0.0, 0.0]
baseline = 10.0
unit = "cm"
"""
    with left.open("rb") as left_file, right.open("rb") as right_file:
        response = web_client.post(
            "/api/sessions/stereo",
            files={
                "left": (left.name, left_file, "image/png"),
                "right": (right.name, right_file, "image/png"),
                "calibration": ("stereo.toml", calibration, "text/plain"),
            },
        )
    assert response.status_code == 200
    session = response.json()

    point = web_client.post(
        "/api/points/stereo",
        json={
            "session_id": session["session_id"],
            "point": [320, 240],
            "manual_right": [160, 240],
            "mode": "length",
            "snapping": False,
        },
    )

    assert point.status_code == 200
    assert point.json()["manual"] is True
    assert point.json()["point_3d"][2] == pytest.approx(50.0)


def _encoded_image(image) -> bytes:
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    return encoded.tobytes()


@pytest.mark.integration
def test_stereo_calibration_requires_matching_pair_counts(
    web_client: TestClient, synthetic_ball_image
) -> None:
    encoded = _encoded_image(synthetic_ball_image)
    response = web_client.post(
        "/api/calibration/stereo",
        files=[
            ("left_images", ("left-1.png", encoded, "image/png")),
            ("left_images", ("left-2.png", encoded, "image/png")),
            ("right_images", ("right-1.png", encoded, "image/png")),
        ],
        data={"columns": "9", "rows": "6", "square_size": "20", "unit": "mm"},
    )

    assert response.status_code == 400
    assert "数量必须一致" in response.json()["detail"]


@pytest.mark.integration
def test_stereo_calibration_requires_six_pairs(
    web_client: TestClient, synthetic_ball_image
) -> None:
    encoded = _encoded_image(synthetic_ball_image)
    files = []
    for index in range(5):
        files.append(("left_images", (f"left-{index}.png", encoded, "image/png")))
        files.append(("right_images", (f"right-{index}.png", encoded, "image/png")))
    response = web_client.post(
        "/api/calibration/stereo",
        files=files,
        data={"columns": "9", "rows": "6", "square_size": "20", "unit": "mm"},
    )

    assert response.status_code == 400
    assert "at least 6" in response.json()["detail"]
