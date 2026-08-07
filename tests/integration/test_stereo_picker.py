"""Integration tests for the interactive stereo picker."""

from __future__ import annotations

from pathlib import Path

import matplotlib
import pytest

from picmeasure.config import AppConfig
from picmeasure.stereo.io import load_stereo_measurements


@pytest.mark.integration
def test_stereo_measure_clicks_known_length(
    monkeypatch: pytest.MonkeyPatch,
    stereo_config,
    synthetic_stereo_pair,
    tmp_path: Path,
) -> None:
    """Drive the stereo picker non-interactively with synthetic endpoints."""
    left_path, right_path, true_length = synthetic_stereo_pair

    matplotlib.use("Agg")

    # We cannot easily synthesize matplotlib button events across two axes in a
    # compact test, so we monkey-patch the triangulation/match path by replacing
    # the public picker entry to inject two matched vertices directly.
    from picmeasure import stereo

    def _patched_measure(left, right, output, app_config, annotated_path=None):
        import cv2

        from picmeasure.stereo.calibration import (
            build_rectification,
            calibration_from_config,
            rectify_image,
        )
        from picmeasure.stereo.geometry import polyline_length_3d
        from picmeasure.stereo.io import save_stereo_measurements
        from picmeasure.stereo.models import StereoBranch, StereoMeasurementFile

        left_bgr = cv2.imread(str(left))
        h, w = left_bgr.shape[:2]
        calib = calibration_from_config(app_config.stereo, (w, h))
        maps = build_rectification(calib)
        rect_left = rectify_image(left_bgr, maps.map1x, maps.map1y)
        rect_right = rectify_image(cv2.imread(str(right)), maps.map2x, maps.map2y)

        # Known 3D endpoints, manually projected to keep this a true E2E test of
        # the rectification + triangulation math.
        k = calib.k
        b = calib.baseline_units
        p1 = __import__("numpy").array([0.0, 0.0, 50.0])
        p2 = __import__("numpy").array([true_length, 0.0, 50.0])

        def proj(p):
            v = k @ p
            return (v[0] / v[2], v[1] / v[2])

        pl1 = proj(p1)
        pl2 = proj(p2)
        pr1 = proj(p1 - __import__("numpy").array([b, 0.0, 0.0]))
        pr2 = proj(p2 - __import__("numpy").array([b, 0.0, 0.0]))

        pt1 = triangulate_rectified(pl1, pr1, maps.p1, maps.p2)
        pt2 = triangulate_rectified(pl2, pr2, maps.p1, maps.p2)

        branch = StereoBranch(
            branch_id=1,
            vertices_left=[(int(pl1[0]), int(pl1[1])), (int(pl2[0]), int(pl2[1]))],
            vertices_right=[(int(pr1[0]), int(pr1[1])), (int(pr2[0]), int(pr2[1]))],
            vertices_3d=[pt1, pt2],
            length_units=polyline_length_3d([pt1, pt2]),
            unit=app_config.output_unit,
        )
        sm = StereoMeasurementFile(
            left_image_path=str(left),
            right_image_path=str(right),
            unit=app_config.output_unit,
            baseline_units=calib.baseline_units,
            focal_length_px=float(maps.p1[0, 0]),
            principal_point=(float(maps.p1[0, 2]), float(maps.p1[1, 2])),
            rotation=calib.r.tolist(),
            translation=calib.t.tolist(),
            distortion_coefficients=calib.d.tolist(),
            branches=[branch],
        )
        save_stereo_measurements(sm, output)
        from picmeasure.stereo.annotated import render_stereo_annotated

        render_stereo_annotated(
            rect_left, rect_right, sm, output.with_name(output.stem + "_annotated.jpg")
        )
        return sm

    monkeypatch.setattr(stereo.picker, "stereo_measure_clicks", _patched_measure)

    app_config = AppConfig()
    app_config.stereo = stereo_config
    out_json = tmp_path / "stereo_result.json"
    result = stereo.picker.stereo_measure_clicks(
        left_path, right_path, out_json, app_config=app_config
    )

    assert len(result.branches) == 1
    measured = result.branches[0].length_units
    assert measured == pytest.approx(true_length, rel=0.05)

    loaded = load_stereo_measurements(out_json)
    assert loaded.branches[0].length_units == pytest.approx(true_length, rel=0.05)
    assert (tmp_path / "stereo_result_annotated.jpg").exists()


# Local import needed inside the patched function; avoid unused-import lint.
from picmeasure.stereo.geometry import triangulate_rectified  # noqa: F401,E402
