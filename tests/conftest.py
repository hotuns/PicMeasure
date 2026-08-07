"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from picmeasure.config import AppConfig, StereoConfig


@pytest.fixture
def synthetic_ball_image() -> np.ndarray:
    """Render a single solid orange-red disk on a white background."""
    img = np.full((600, 800, 3), 255, dtype=np.uint8)
    cv2.circle(img, (400, 300), 60, (60, 110, 230), thickness=-1)
    return img


@pytest.fixture
def synthetic_ball_path(synthetic_ball_image: np.ndarray, tmp_path: Path) -> Path:
    """Save the synthetic ball image to a temporary PNG file."""
    path = tmp_path / "synthetic_ball.png"
    cv2.imwrite(str(path), synthetic_ball_image)
    return path


@pytest.fixture
def default_config() -> AppConfig:
    """Return a default AppConfig instance."""
    return AppConfig()


@pytest.fixture
def stereo_config() -> StereoConfig:
    """Return a plausible stereo config for synthetic tests."""
    return StereoConfig(
        enabled=True,
        focal_length_px=800.0,
        principal_point=(320.0, 240.0),
        rotation=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        translation=[10.0, 0.0, 0.0],
        baseline=10.0,
        unit="cm",
    )


@pytest.fixture
def synthetic_stereo_pair(stereo_config: StereoConfig, tmp_path: Path) -> tuple[Path, Path, float]:
    """Create a synthetic rectified stereo pair with a known 3D segment.

    Returns left image path, right image path, and the true segment length in cm.
    """
    k = stereo_config.camera_matrix_array()
    b = stereo_config.baseline_units

    width, height = 640, 480
    left_img = np.full((height, width, 3), 255, dtype=np.uint8)
    right_img = np.full((height, width, 3), 255, dtype=np.uint8)

    # 3D segment endpoints in left-camera frame, 50 cm away, 10 cm long.
    p1 = np.array([0.0, 0.0, 50.0], dtype=np.float64)
    p2 = np.array([10.0, 0.0, 50.0], dtype=np.float64)
    true_length = float(np.linalg.norm(p2 - p1))

    # Project to left image.
    pl1 = k @ p1
    pl2 = k @ p2
    pl1 = (pl1 / pl1[2])[:2].astype(int)
    pl2 = (pl2 / pl2[2])[:2].astype(int)

    # Project to right image (R=I, T=[-B,0,0] for point in right frame).
    pr1_3d = p1 - np.array([b, 0.0, 0.0])
    pr2_3d = p2 - np.array([b, 0.0, 0.0])
    pr1 = k @ pr1_3d
    pr2 = k @ pr2_3d
    pr1 = (pr1 / pr1[2])[:2].astype(int)
    pr2 = (pr2 / pr2[2])[:2].astype(int)

    color = (0, 0, 0)
    thickness = 5
    cv2.line(left_img, tuple(pl1), tuple(pl2), color, thickness)
    cv2.line(right_img, tuple(pr1), tuple(pr2), color, thickness)

    # Add some texture around the line to help NCC matching.
    rng = np.random.default_rng(42)
    noise = rng.integers(0, 40, (height, width, 3), dtype=np.uint8)
    left_img = cv2.subtract(left_img, noise)
    noise = rng.integers(0, 40, (height, width, 3), dtype=np.uint8)
    right_img = cv2.subtract(right_img, noise)

    left_path = tmp_path / "synth_left.png"
    right_path = tmp_path / "synth_right.png"
    cv2.imwrite(str(left_path), left_img)
    cv2.imwrite(str(right_path), right_img)
    return left_path, right_path, true_length
