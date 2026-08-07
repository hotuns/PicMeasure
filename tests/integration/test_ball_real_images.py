"""Regression coverage for reference balls in the repository sample images."""

from __future__ import annotations

from pathlib import Path

import cv2
import pytest

from picmeasure.ball.detector import BallDetector
from picmeasure.config import BallConfig


@pytest.mark.integration
@pytest.mark.parametrize(
    ("filename", "expected_center"),
    [
        ("0730-1.jpg", (485, 1715)),
        ("0730-2.jpg", (813, 1722)),
        ("1.jpg", (1933, 1121)),
        ("2.jpg", (1945, 1117)),
        ("3.jpg", (1527, 426)),
        ("4.jpg", (1498, 1784)),
        ("IMG_20260730_163858.jpg", (1507, 2368)),
    ],
)
def test_real_reference_ball_is_first_candidate(
    filename: str, expected_center: tuple[int, int]
) -> None:
    path = Path(__file__).parents[2] / "datas" / filename
    image = cv2.imread(str(path))
    candidates = BallDetector(BallConfig()).detect_candidates(image)

    assert candidates
    center = candidates[0].center_xy
    assert abs(center[0] - expected_center[0]) <= 5
    assert abs(center[1] - expected_center[1]) <= 5
