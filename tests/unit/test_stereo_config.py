"""Unit tests for stereo configuration validation."""

from __future__ import annotations

import pytest

from picmeasure.config import CameraCalibrationConfig, CorrespondenceConfig, StereoConfig


@pytest.mark.unit
def test_correspondence_window_size_must_be_odd() -> None:
    with pytest.raises(ValueError, match="odd"):
        CorrespondenceConfig(window_size=10)


@pytest.mark.unit
def test_correspondence_window_size_minimum() -> None:
    with pytest.raises(ValueError, match="odd"):
        CorrespondenceConfig(window_size=1)
    cfg = CorrespondenceConfig(window_size=3)
    assert cfg.window_size == 3


@pytest.mark.unit
def test_stereo_config_builds_camera_matrix() -> None:
    cfg = StereoConfig(
        enabled=True,
        focal_length_px=800.0,
        principal_point=(320.0, 240.0),
        translation=[10.0, 0.0, 0.0],
        baseline=10.0,
    )
    k = cfg.camera_matrix_array()
    assert k[0, 0] == 800.0
    assert k[1, 1] == 800.0
    assert k[0, 2] == 320.0
    assert k[1, 2] == 240.0


@pytest.mark.unit
def test_stereo_config_rejects_non_so3_rotation() -> None:
    with pytest.raises(ValueError, match="orthogonal"):
        StereoConfig(
            enabled=True,
            focal_length_px=800.0,
            principal_point=(320.0, 240.0),
            rotation=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 2.0]],
            translation=[10.0, 0.0, 0.0],
        )


@pytest.mark.unit
def test_stereo_config_rejects_baseline_mismatch() -> None:
    with pytest.raises(ValueError, match="baseline"):
        StereoConfig(
            enabled=True,
            focal_length_px=800.0,
            principal_point=(320.0, 240.0),
            translation=[10.0, 0.0, 0.0],
            baseline=5.0,
        )


@pytest.mark.unit
def test_stereo_config_rejects_zero_translation() -> None:
    with pytest.raises(ValueError, match="non-zero"):
        StereoConfig(
            enabled=True,
            focal_length_px=800.0,
            principal_point=(320.0, 240.0),
            translation=[0.0, 0.0, 0.0],
        )


@pytest.mark.unit
def test_stereo_config_alpha_range() -> None:
    with pytest.raises(ValueError, match="alpha"):
        StereoConfig(alpha=1.5)


@pytest.mark.unit
def test_stereo_config_optional_camera_matrix() -> None:
    cfg = StereoConfig(
        enabled=True,
        camera_matrix=[[800.0, 0.0, 320.0], [0.0, 800.0, 240.0], [0.0, 0.0, 1.0]],
        translation=[10.0, 0.0, 0.0],
    )
    k = cfg.camera_matrix_array()
    assert k[0, 0] == 800.0


@pytest.mark.unit
def test_stereo_config_supports_independent_camera_intrinsics() -> None:
    left = CameraCalibrationConfig(
        camera_matrix=[[800.0, 0.0, 320.0], [0.0, 801.0, 240.0], [0.0, 0.0, 1.0]],
        distortion_coefficients=[0.1, 0.0, 0.0, 0.0, 0.0],
        rms_error=0.2,
    )
    right = CameraCalibrationConfig(
        camera_matrix=[[810.0, 0.0, 318.0], [0.0, 812.0, 242.0], [0.0, 0.0, 1.0]],
        distortion_coefficients=[0.2, 0.0, 0.0, 0.0, 0.0],
        rms_error=0.3,
    )
    cfg = StereoConfig(left=left, right=right, translation=[10.0, 0.0, 0.0])

    assert cfg.camera_matrix_array("left")[0, 0] == 800.0
    assert cfg.camera_matrix_array("right")[0, 0] == 810.0
    assert cfg.distortion_array("left")[0] == 0.1
    assert cfg.distortion_array("right")[0] == 0.2


@pytest.mark.unit
def test_legacy_shared_intrinsics_apply_to_both_cameras() -> None:
    cfg = StereoConfig(
        camera_matrix=[[800.0, 0.0, 320.0], [0.0, 800.0, 240.0], [0.0, 0.0, 1.0]],
        distortion_coefficients=[0.1, 0.0, 0.0, 0.0, 0.0],
        translation=[10.0, 0.0, 0.0],
    )

    assert (cfg.camera_matrix_array("left") == cfg.camera_matrix_array("right")).all()
    assert (cfg.distortion_array("left") == cfg.distortion_array("right")).all()
