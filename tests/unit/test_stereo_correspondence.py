"""Unit tests for sparse epipolar correspondence search."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from picmeasure.config import CorrespondenceConfig
from picmeasure.stereo.calibration import (
    build_rectification,
    calibration_from_config,
    rectify_image,
)
from picmeasure.stereo.correspondence import match_along_epipolar_line


@pytest.mark.unit
def test_match_along_epipolar_line_finds_known_disparity(
    stereo_config, synthetic_stereo_pair
) -> None:
    left_path, right_path, _ = synthetic_stereo_pair
    left_bgr = cv2.imread(str(left_path))
    right_bgr = cv2.imread(str(right_path))

    calib = calibration_from_config(stereo_config, (left_bgr.shape[1], left_bgr.shape[0]))
    maps = build_rectification(calib)
    rect_left = rectify_image(left_bgr, maps.map1x, maps.map1y)
    rect_right = rectify_image(right_bgr, maps.map2x, maps.map2y)

    # Pick a point near the middle of the line on the left image.
    h, w = rect_left.shape[:2]
    left_pt = (w // 2, h // 2)

    cfg = CorrespondenceConfig(window_size=11, search_range_px=200)
    match = match_along_epipolar_line(rect_left, rect_right, left_pt, cfg)

    # Expected disparity for a point at Z=50 cm with B=10 cm, f=800 px.
    expected_disparity = 800.0 * 10.0 / 50.0  # = 160 px
    actual_disparity = left_pt[0] - match.right_pt[0]
    assert actual_disparity == pytest.approx(expected_disparity, abs=5.0)
    assert match.score > 0.5


@pytest.mark.unit
def test_match_rejects_border_points(stereo_config, synthetic_stereo_pair) -> None:
    left_path, _, _ = synthetic_stereo_pair
    left_bgr = cv2.imread(str(left_path))
    cfg = CorrespondenceConfig(window_size=21)
    with pytest.raises(RuntimeError, match="border"):
        match_along_epipolar_line(left_bgr, left_bgr, (5, 5), cfg)


@pytest.mark.unit
def test_match_rejects_repetitive_checkerboard_texture() -> None:
    yy, xx = np.indices((120, 320))
    checker = (((xx // 10) + (yy // 10)) % 2 * 255).astype(np.uint8)
    cfg = CorrespondenceConfig(window_size=11, search_range_px=100)

    with pytest.raises(RuntimeError, match="not unique"):
        match_along_epipolar_line(checker, checker, (200, 60), cfg)


@pytest.mark.unit
def test_default_search_range_supports_long_focal_length_rigs() -> None:
    assert CorrespondenceConfig().search_range_px >= 600


@pytest.mark.unit
def test_zero_match_score_returns_domain_error(monkeypatch: pytest.MonkeyPatch) -> None:
    image = np.arange(120 * 320, dtype=np.uint8).reshape(120, 320)
    monkeypatch.setattr(
        cv2,
        "matchTemplate",
        lambda *_args, **_kwargs: np.zeros((1, 101), dtype=np.float32),
    )

    with pytest.raises(RuntimeError, match="insufficient matching texture"):
        match_along_epipolar_line(
            image,
            image,
            (200, 60),
            CorrespondenceConfig(window_size=11, search_range_px=100),
        )
