"""Unit tests for the click-based ruler tool.

These tests cover the pure-Python parts of :mod:`picmeasure.clickmeasure`
(polyline math, JSON round-trip, annotated-image rendering). The
interactive matplotlib loop is exercised by feeding it a no-op
``plt.show`` and asserting that an empty session returns cleanly with
the calibrated scale populated.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import cv2
import numpy as np
import pytest

from picmeasure.clickmeasure.picker import (
    BranchPolyline,
    DiameterMeasurement,
    MeasurementFile,
    load_measurements,
    measure_clicks,
    polyline_length_pixels,
    save_measurements,
    write_annotated_image,
)
from picmeasure.config import AppConfig


@pytest.mark.unit
def test_polyline_length_handles_empty_and_single_point() -> None:
    assert polyline_length_pixels([]) == 0.0
    assert polyline_length_pixels([(0, 0)]) == 0.0


@pytest.mark.unit
def test_polyline_length_two_point_distance() -> None:
    assert polyline_length_pixels([(0, 0), (3, 4)]) == pytest.approx(5.0)


@pytest.mark.unit
def test_polyline_length_sums_segments() -> None:
    pts = [(0, 0), (3, 4), (3, 4 + 12)]
    expected = 5.0 + 12.0
    assert polyline_length_pixels(pts) == pytest.approx(expected)


@pytest.mark.unit
def test_polyline_length_diagonal_zigzag() -> None:
    pts = [(0, 0), (10, 10), (0, 20)]
    assert polyline_length_pixels(pts) == pytest.approx(2 * math.hypot(10, 10))


@pytest.mark.unit
def test_save_and_load_measurements_roundtrip(tmp_path: Path) -> None:
    mf = MeasurementFile(
        image_path="datas/1.jpg",
        pixels_per_unit=6.27,
        unit="cm",
        ball_center_xy=(1933, 1121),
        ball_radius_px=47.0,
        branches=[
            BranchPolyline(
                branch_id=1,
                vertices=[(100, 200), (400, 250)],
                length_pixels=304.14,
                length_units=48.51,
                unit="cm",
            ),
        ],
    )
    out = tmp_path / "m.json"
    save_measurements(mf, out)

    raw = json.loads(out.read_text(encoding="utf-8"))
    assert raw["schema_version"] == 2
    assert raw["calibration"]["pixels_per_unit"] == 6.27
    assert raw["branches"][0]["length_units"] == pytest.approx(48.51)

    loaded = load_measurements(out)
    assert loaded.image_path == "datas/1.jpg"
    assert loaded.pixels_per_unit == 6.27
    assert loaded.unit == "cm"
    assert loaded.ball_center_xy == (1933, 1121)
    assert loaded.branches[0].vertices == [(100, 200), (400, 250)]
    assert loaded.branches[0].length_units == pytest.approx(48.51)


@pytest.mark.unit
def test_save_omits_empty_branches(tmp_path: Path) -> None:
    mf = MeasurementFile(
        image_path="x.jpg",
        pixels_per_unit=10.0,
        unit="cm",
        ball_center_xy=None,
        ball_radius_px=None,
        branches=[
            BranchPolyline(branch_id=1, vertices=[]),
            BranchPolyline(branch_id=2, vertices=[(1, 2), (3, 4)]),
        ],
    )
    out = tmp_path / "m.json"
    save_measurements(mf, out)
    raw = json.loads(out.read_text(encoding="utf-8"))
    assert len(raw["branches"]) == 1
    assert raw["branches"][0]["branch_id"] == 2


@pytest.mark.unit
def test_write_annotated_image_produces_a_file(
    synthetic_ball_image: np.ndarray, tmp_path: Path
) -> None:
    mf = MeasurementFile(
        image_path="synthetic.png",
        pixels_per_unit=8.0,
        unit="cm",
        ball_center_xy=(400, 300),
        ball_radius_px=60.0,
        branches=[
            BranchPolyline(
                branch_id=1,
                vertices=[(100, 100), (300, 200)],
                length_pixels=223.6,
                length_units=27.95,
                unit="cm",
            ),
        ],
    )
    out = tmp_path / "annotated.jpg"
    write_annotated_image(synthetic_ball_image, mf, out)

    assert out.exists()
    rendered = cv2.imread(str(out))
    assert rendered is not None
    assert rendered.shape[0] == synthetic_ball_image.shape[0]
    assert rendered.shape[1] == synthetic_ball_image.shape[1] + 300


@pytest.mark.integration
def test_measure_clicks_initialises_with_ball_calibration(
    monkeypatch: pytest.MonkeyPatch,
    synthetic_ball_path: Path,
    tmp_path: Path,
) -> None:
    """Drive the picker non-interactively: plt.show is a no-op so the
    session ends with no clicks; we assert calibration succeeded."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from picmeasure.ball import confirmation
    from picmeasure.ball.detector import BallDetector

    monkeypatch.setattr(plt, "show", lambda *a, **k: None)
    confirmed = BallDetector(AppConfig().ball).detect(cv2.imread(str(synthetic_ball_path)))
    monkeypatch.setattr(confirmation, "confirm_reference_ball", lambda *a, **k: confirmed)

    cfg = AppConfig()
    out_json = tmp_path / "m.json"
    result = measure_clicks(synthetic_ball_path, out_json, app_config=cfg)

    assert result.pixels_per_unit is not None
    assert result.pixels_per_unit == pytest.approx(2 * 60 / 4.0, rel=0.10)
    assert result.unit == "cm"
    assert result.ball_center_xy is not None
    assert result.branches == []
    # No clicks → no JSON file written.
    assert not out_json.exists()


@pytest.mark.integration
def test_measure_clicks_raises_when_no_ball(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A pure-white image has no ball — expect a clear error."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from picmeasure.ball import confirmation

    monkeypatch.setattr(plt, "show", lambda *a, **k: None)
    monkeypatch.setattr(confirmation, "confirm_reference_ball", lambda *a, **k: None)

    blank = np.full((400, 400, 3), 255, dtype=np.uint8)
    blank_path = tmp_path / "blank.png"
    cv2.imwrite(str(blank_path), blank)

    with pytest.raises(RuntimeError, match="检测到参考球"):
        measure_clicks(blank_path, tmp_path / "m.json", app_config=AppConfig())


@pytest.mark.unit
def test_v2_roundtrip_preserves_diameter(tmp_path: Path) -> None:
    mf = MeasurementFile(
        image_path="branch.jpg",
        pixels_per_unit=10.0,
        unit="cm",
        ball_center_xy=(20, 20),
        ball_radius_px=20.0,
        ball_source="manual",
        branches=[
            BranchPolyline(
                branch_id=1,
                diameter_measurements=[
                    DiameterMeasurement(1, ((10, 10), (10, 30)), 20.0, 2.0, "cm")
                ],
            )
        ],
    )
    path = tmp_path / "v2.json"
    save_measurements(mf, path)
    loaded = load_measurements(path)

    assert loaded.ball_source == "manual"
    assert loaded.branches[0].diameter_measurements[0].diameter_units == pytest.approx(2.0)


@pytest.mark.unit
def test_load_legacy_result_migrates_in_memory(tmp_path: Path) -> None:
    legacy = {
        "image_path": "legacy.jpg",
        "scale": {"pixels_per_unit": 5.0, "unit": "cm"},
        "branches": [{"branch_id": 1, "vertices": [[1, 2]], "length_units": 0, "unit": "cm"}],
    }
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(legacy), encoding="utf-8")
    loaded = load_measurements(path)

    assert loaded.image_path == "legacy.jpg"
    assert loaded.branches[0].diameter_measurements == []
