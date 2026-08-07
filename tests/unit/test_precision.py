"""Tests for edge-assisted point selection."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from picmeasure.config import PrecisionConfig
from picmeasure.precision import PointPreview, magnifier_crop, snap_to_centerline, snap_to_edge


@pytest.mark.unit
def test_snap_to_edge_finds_step_within_two_pixels() -> None:
    image = np.zeros((80, 80, 3), dtype=np.uint8)
    image[:, 40:] = 255
    preview = snap_to_edge(image, (44, 40), PrecisionConfig(min_edge_score=10))
    assert preview.snapped
    assert abs(preview.candidate[0] - 40) <= 2


@pytest.mark.unit
def test_snap_to_edge_falls_back_on_flat_image() -> None:
    image = np.full((40, 40, 3), 100, dtype=np.uint8)
    preview = snap_to_edge(image, (20, 20), PrecisionConfig(min_edge_score=10))
    assert preview.candidate == (20, 20)
    assert not preview.snapped


@pytest.mark.unit
def test_centerline_uses_midpoint_of_opposing_edges() -> None:
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    cv2.rectangle(image, (35, 0), (55, 99), (255, 255, 255), -1)
    preview = snap_to_centerline(
        image, (48, 60), (48, 30), PrecisionConfig(snap_radius_px=15, min_edge_score=10)
    )
    assert preview.snapped
    assert abs(preview.candidate[0] - 45) <= 2


@pytest.mark.unit
def test_preview_nudge_clamps_to_image() -> None:
    preview = PointPreview((0, 0), (0, 0), True)
    preview.nudge(-5, 200, (20, 30, 3))
    assert preview.candidate == (0, 19)
    assert not preview.snapped


@pytest.mark.unit
def test_magnifier_crop_preserves_source_coordinates_at_border() -> None:
    image = np.zeros((20, 30, 3), dtype=np.uint8)
    crop, origin = magnifier_crop(image, (1, 1), 5)
    assert origin == (0, 0)
    assert crop.shape[:2] == (7, 7)
