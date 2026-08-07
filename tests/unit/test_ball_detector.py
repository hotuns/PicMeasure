"""Unit tests for the orange-red reference-ball detector."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from picmeasure.ball.detector import BallDetector
from picmeasure.config import BallConfig


def _synthetic_ball_image(
    radius_px: int,
    image_size: tuple[int, int] = (800, 600),
    center: tuple[int, int] | None = None,
    bgr: tuple[int, int, int] = (60, 110, 230),  # BGR for an orange-red
) -> np.ndarray:
    """Render a single solid orange-red disk on a white background."""
    h, w = image_size
    img = np.full((h, w, 3), 255, dtype=np.uint8)
    cx, cy = center if center is not None else (w // 2, h // 2)
    cv2.circle(img, (cx, cy), radius_px, bgr, thickness=-1)
    return img


@pytest.mark.unit
def test_detects_ball_and_derives_correct_scale() -> None:
    radius = 60
    img = _synthetic_ball_image(radius_px=radius)
    cfg = BallConfig(known_diameter_cm=15.0)

    result = BallDetector(cfg).detect(img)

    assert result.detected
    assert result.ball_radius_px is not None
    assert result.pixels_per_unit is not None
    # Detector should recover the radius to within a few percent (Hough is
    # not pixel-exact on a rasterised disk).
    assert abs(result.ball_radius_px - radius) / radius < 0.10
    expected_px_per_cm = 2.0 * radius / cfg.known_diameter_cm
    assert abs(result.pixels_per_unit - expected_px_per_cm) / expected_px_per_cm < 0.10


@pytest.mark.unit
def test_no_orange_pixels_returns_not_detected() -> None:
    img = np.full((400, 400, 3), 255, dtype=np.uint8)  # pure white, no ball
    result = BallDetector(BallConfig()).detect(img)
    assert not result.detected
    assert result.error_message is not None


@pytest.mark.unit
def test_empty_image_returns_not_detected() -> None:
    empty = np.zeros((0, 0, 3), dtype=np.uint8)
    result = BallDetector(BallConfig()).detect(empty)
    assert not result.detected


@pytest.mark.unit
def test_center_is_recovered_within_a_few_pixels() -> None:
    radius = 50
    center = (300, 200)
    img = _synthetic_ball_image(radius_px=radius, center=center)

    result = BallDetector(BallConfig()).detect(img)

    assert result.detected
    assert result.ball_center_xy is not None
    cx, cy = result.ball_center_xy
    assert abs(cx - center[0]) <= 5
    assert abs(cy - center[1]) <= 5


@pytest.mark.unit
def test_known_diameter_scaling() -> None:
    """A 6cm reference ball should produce 2x the px/cm of a 12cm ball at same radius."""
    img = _synthetic_ball_image(radius_px=60)

    fine = BallDetector(BallConfig(known_diameter_cm=6.0)).detect(img)
    coarse = BallDetector(BallConfig(known_diameter_cm=12.0)).detect(img)

    assert fine.detected and coarse.detected
    assert fine.pixels_per_unit is not None
    assert coarse.pixels_per_unit is not None
    assert abs(fine.pixels_per_unit / coarse.pixels_per_unit - 2.0) < 0.05


def test_red_rectangle_is_not_a_ball_candidate() -> None:
    img = np.full((400, 400, 3), 255, dtype=np.uint8)
    cv2.rectangle(img, (80, 170), (320, 230), (60, 110, 230), -1)
    assert BallDetector(BallConfig()).detect_candidates(img) == []


def test_multiple_circles_are_ranked_deterministically() -> None:
    img = np.full((400, 500, 3), 255, dtype=np.uint8)
    cv2.circle(img, (130, 200), 45, (60, 110, 230), -1)
    cv2.circle(img, (360, 200), 60, (60, 110, 230), -1)
    detector = BallDetector(BallConfig())
    first = detector.detect_candidates(img)
    second = detector.detect_candidates(img)
    assert [c.center_xy for c in first] == [c.center_xy for c in second]
    assert len(first) >= 2


@pytest.mark.unit
def test_detects_light_colored_ball_without_red_pixels() -> None:
    img = np.full((480, 640, 3), 90, dtype=np.uint8)
    cv2.circle(img, (320, 240), 62, (230, 235, 238), -1)
    cv2.circle(img, (300, 220), 14, (250, 250, 250), -1)

    candidates = BallDetector(BallConfig()).detect_candidates(img)

    assert candidates
    assert abs(candidates[0].center_xy[0] - 320) <= 5
    assert abs(candidates[0].center_xy[1] - 240) <= 5
    assert abs(candidates[0].radius_px - 62) <= 6
