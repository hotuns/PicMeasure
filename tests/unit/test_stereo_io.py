"""Unit tests for stereo JSON persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from picmeasure.stereo.geometry import Point3D
from picmeasure.stereo.io import load_stereo_measurements, save_stereo_measurements
from picmeasure.stereo.models import (
    StereoBranch,
    StereoDiameterMeasurement,
    StereoMeasurementFile,
)


@pytest.mark.unit
def test_save_and_load_stereo_measurements_roundtrip(tmp_path: Path) -> None:
    sm = StereoMeasurementFile(
        left_image_path="left.jpg",
        right_image_path="right.jpg",
        unit="cm",
        baseline_units=10.0,
        focal_length_px=800.0,
        principal_point=(320.0, 240.0),
        rotation=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        translation=[10.0, 0.0, 0.0],
        distortion_coefficients=[0.0] * 5,
        reprojection_error_px=0.35,
        triangulated_ball_diameter_units=4.02,
        branches=[
            StereoBranch(
                branch_id=1,
                vertices_left=[(100, 200), (200, 200)],
                vertices_right=[(80, 200), (180, 200)],
                vertices_3d=[Point3D(0, 0, 50), Point3D(10, 0, 50)],
                length_units=10.0,
                unit="cm",
                diameter_measurements=[
                    StereoDiameterMeasurement(
                        section_id=1,
                        edges_left=((100, 190), (100, 210)),
                        edges_right=((80, 190), (80, 210)),
                        edges_3d=(Point3D(0, -1, 50), Point3D(0, 1, 50)),
                        diameter_units=2.0,
                        unit="cm",
                    )
                ],
            ),
        ],
    )
    out = tmp_path / "stereo.json"
    save_stereo_measurements(sm, out)

    loaded = load_stereo_measurements(out)
    assert loaded.left_image_path == "left.jpg"
    assert loaded.right_image_path == "right.jpg"
    assert loaded.baseline_units == 10.0
    assert loaded.focal_length_px == 800.0
    assert loaded.reprojection_error_px == pytest.approx(0.35)
    assert loaded.triangulated_ball_diameter_units == pytest.approx(4.02)
    assert len(loaded.branches) == 1
    assert loaded.branches[0].length_units == pytest.approx(10.0)
    assert len(loaded.branches[0].vertices_3d) == 2
    assert loaded.branches[0].diameter_measurements[0].diameter_units == pytest.approx(2.0)


@pytest.mark.unit
def test_save_omits_empty_branches(tmp_path: Path) -> None:
    sm = StereoMeasurementFile(
        left_image_path="left.jpg",
        right_image_path="right.jpg",
        unit="cm",
        baseline_units=10.0,
        focal_length_px=800.0,
        principal_point=(320.0, 240.0),
        rotation=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        translation=[10.0, 0.0, 0.0],
        distortion_coefficients=[0.0] * 5,
        branches=[
            StereoBranch(branch_id=1, unit="cm"),
            StereoBranch(
                branch_id=2,
                vertices_left=[(1, 2)],
                vertices_right=[(3, 4)],
                vertices_3d=[Point3D(0, 0, 50)],
                unit="cm",
            ),
        ],
    )
    out = tmp_path / "stereo.json"
    save_stereo_measurements(sm, out)

    loaded = load_stereo_measurements(out)
    assert len(loaded.branches) == 1
    assert loaded.branches[0].branch_id == 2
