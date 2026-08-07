"""Unit tests for stereo rectification."""

from __future__ import annotations

import cv2
import pytest

from picmeasure.config import StereoConfig
from picmeasure.stereo.calibration import build_rectification, calibration_from_config


@pytest.mark.unit
def test_build_rectification_passes_translation_as_column_vector(
    stereo_config: StereoConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenCV 5 requires T to use its documented 3x1 vector shape."""
    original_stereo_rectify = cv2.stereoRectify
    observed_shape: tuple[int, ...] | None = None

    def record_translation_shape(*args: object, **kwargs: object) -> tuple[object, ...]:
        nonlocal observed_shape
        translation = kwargs["T"]
        observed_shape = translation.shape  # type: ignore[union-attr]
        return original_stereo_rectify(*args, **kwargs)

    monkeypatch.setattr(cv2, "stereoRectify", record_translation_shape)

    calib = calibration_from_config(stereo_config, (640, 480))
    build_rectification(calib)

    assert observed_shape == (3, 1)


@pytest.mark.unit
def test_build_rectification_produces_valid_maps(stereo_config: StereoConfig) -> None:
    image_size = (640, 480)
    calib = calibration_from_config(stereo_config, image_size)
    maps = build_rectification(calib)

    assert maps.p1.shape == (3, 4)
    assert maps.p2.shape == (3, 4)
    assert maps.q.shape == (4, 4)
    assert maps.map1x.shape[:2] == (480, 640)
    assert maps.map1y.shape[:2] == (480, 640)
    assert maps.map2x.shape[:2] == (480, 640)
    assert maps.map2y.shape[:2] == (480, 640)


@pytest.mark.unit
def test_rectification_preserves_focal_length(stereo_config: StereoConfig) -> None:
    image_size = (640, 480)
    calib = calibration_from_config(stereo_config, image_size)
    maps = build_rectification(calib)

    assert maps.p1[0, 0] == pytest.approx(stereo_config.focal_length_px, rel=0.05)
    assert maps.p2[0, 0] == pytest.approx(stereo_config.focal_length_px, rel=0.05)


@pytest.mark.unit
def test_rectification_baseline_in_p2(stereo_config: StereoConfig) -> None:
    image_size = (640, 480)
    calib = calibration_from_config(stereo_config, image_size)
    maps = build_rectification(calib)

    f = maps.p1[0, 0]
    baseline_from_p2 = abs(float(maps.p2[0, 3])) / f
    assert baseline_from_p2 == pytest.approx(stereo_config.baseline_units, rel=0.01)
