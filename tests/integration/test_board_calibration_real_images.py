"""Regression coverage for real chessboard calibration images."""

from __future__ import annotations

from pathlib import Path

import cv2
import pytest

from picmeasure.stereo.board_calibration import _find_corners


@pytest.mark.integration
def test_finds_large_9_by_6_square_board_near_image_edge() -> None:
    path = (
        Path(__file__).parents[2]
        / "images/0803枝条拍照/161左0803标定定焦12mm焦距距离3m/20260803141731.jpg"
    )
    image = cv2.imread(str(path))

    corners = _find_corners(image, (8, 5))

    assert corners is not None
    assert corners.shape == (40, 2)
