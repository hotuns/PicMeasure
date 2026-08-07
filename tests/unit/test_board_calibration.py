"""Tests for chessboard calibration export."""

from __future__ import annotations

import tomllib

import cv2
import numpy as np
import pytest

from picmeasure.config import (
    CalibrationQualityConfig,
    CameraCalibrationConfig,
    StereoConfig,
)
from picmeasure.stereo.board_calibration import (
    _canonicalize_corner_order,
    _inlier_pair_indices,
    _mean_reprojection_error,
    stereo_config_to_toml,
)


@pytest.mark.unit
def test_corner_order_is_canonicalized_from_top_left() -> None:
    corners = np.array([[90.0, 80.0], [50.0, 50.0], [10.0, 20.0]], dtype=np.float32)

    ordered = _canonicalize_corner_order(corners)

    assert ordered[0].tolist() == [10.0, 20.0]
    assert ordered[-1].tolist() == [90.0, 80.0]


@pytest.mark.unit
def test_geometric_outlier_pairs_are_rejected() -> None:
    errors = [0.2, 0.3, 0.4, 0.5, 6.0, 17.0]

    assert _inlier_pair_indices(errors) == [0, 1, 2, 3]


@pytest.mark.unit
def test_reprojection_error_accepts_opencv5_flat_corner_shape() -> None:
    objects = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32)
    rotation = np.zeros((3, 1), dtype=np.float64)
    translation = np.array([[0.0], [0.0], [5.0]], dtype=np.float64)
    matrix = np.array([[800.0, 0.0, 320.0], [0.0, 800.0, 240.0], [0.0, 0.0, 1.0]])
    distortion = np.zeros(5)
    projected, _ = cv2.projectPoints(objects, rotation, translation, matrix, distortion)
    observed = projected.reshape(-1, 2).astype(np.float32)

    error = _mean_reprojection_error(
        [objects], [observed], (rotation,), (translation,), matrix, distortion
    )

    assert error == pytest.approx(0.0)


@pytest.mark.unit
def test_exported_stereo_toml_round_trips() -> None:
    camera = CameraCalibrationConfig(
        camera_matrix=[[800.0, 0.0, 320.0], [0.0, 801.0, 240.0], [0.0, 0.0, 1.0]],
        distortion_coefficients=[0.1, -0.02, 0.0, 0.0, 0.0],
        rms_error=0.25,
    )
    config = StereoConfig(
        enabled=True,
        image_size=(640, 480),
        left=camera,
        right=camera.model_copy(update={"rms_error": 0.3}),
        rotation=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        translation=[-60.0, 0.0, 0.0],
        baseline=60.0,
        unit="mm",
        quality=CalibrationQualityConfig(
            valid_pairs=12,
            total_pairs=15,
            stereo_rms_error=0.4,
            rectified_median_vertical_error_px=0.2,
            rectified_p90_vertical_error_px=0.6,
        ),
    )

    raw = tomllib.loads(stereo_config_to_toml(config))["stereo"]
    restored = StereoConfig(**raw)

    assert restored.image_size == (640, 480)
    assert restored.camera_matrix_array("left")[0, 0] == 800.0
    assert restored.camera_matrix_array("right")[1, 1] == 801.0
    assert restored.baseline_units == pytest.approx(60.0)
    assert restored.quality is not None
    assert restored.quality.valid_pairs == 12
