"""Unit tests for stereo geometry (triangulation, 3D length)."""

from __future__ import annotations

import numpy as np
import pytest

from picmeasure.config import StereoConfig
from picmeasure.stereo.calibration import build_rectification, calibration_from_config
from picmeasure.stereo.geometry import (
    Point3D,
    polyline_length_3d,
    project_point,
    triangulate_rectified,
)


@pytest.mark.unit
def test_triangulate_rectified_round_trip(stereo_config: StereoConfig) -> None:
    image_size = (640, 480)
    calib = calibration_from_config(stereo_config, image_size)
    maps = build_rectification(calib)

    # Known 3D point in left-camera frame.
    p3d = Point3D(x=5.0, y=2.0, z=50.0)
    k = calib.k

    # Project to left and right images.
    pl = project_point(p3d.array(), k)
    pr = project_point(p3d.array() - calib.t, k)

    reconstructed = triangulate_rectified(pl, pr, maps.p1, maps.p2)
    assert reconstructed.x == pytest.approx(p3d.x, rel=1e-3)
    assert reconstructed.y == pytest.approx(p3d.y, rel=1e-3)
    assert reconstructed.z == pytest.approx(p3d.z, rel=1e-3)


@pytest.mark.unit
def test_polyline_length_3d_sums_segments() -> None:
    pts = [Point3D(0, 0, 0), Point3D(3, 4, 0), Point3D(3, 4, 12)]
    assert polyline_length_3d(pts) == pytest.approx(5.0 + 12.0)


@pytest.mark.unit
def test_polyline_length_3d_empty_or_single() -> None:
    assert polyline_length_3d([]) == 0.0
    assert polyline_length_3d([Point3D(1, 2, 3)]) == 0.0


@pytest.mark.unit
def test_triangulate_rectified_rejects_zero_disparity() -> None:
    p1 = np.array([[800.0, 0.0, 320.0, 0.0], [0.0, 800.0, 240.0, 0.0], [0.0, 0.0, 1.0, 0.0]])
    p2 = np.array([[800.0, 0.0, 320.0, -9600.0], [0.0, 800.0, 240.0, 0.0], [0.0, 0.0, 1.0, 0.0]])
    with pytest.raises(ValueError, match="disparity"):
        triangulate_rectified((320.0, 240.0), (320.0, 240.0), p1, p2)
