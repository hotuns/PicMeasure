"""Reference-ball confirmation helpers."""

from __future__ import annotations

import pytest

from picmeasure.ball.confirmation import manual_ball_result, result_from_candidate
from picmeasure.ball.models import BallCandidate
from picmeasure.config import BallConfig


@pytest.mark.unit
def test_manual_center_and_edge_define_scale() -> None:
    result = manual_ball_result((10, 10), (10, 30), BallConfig(known_diameter_cm=4))
    assert result.source == "manual"
    assert result.ball_radius_px == pytest.approx(20)
    assert result.pixels_per_unit == pytest.approx(10)


@pytest.mark.unit
def test_confirmed_candidate_retains_score() -> None:
    candidate = BallCandidate((50, 50), 20, 0.86, 0.9, 0.8, 0.85, 0.9, "hough")
    result = result_from_candidate(candidate, BallConfig(known_diameter_cm=4))
    assert result.source == "auto"
    assert result.candidate_score == pytest.approx(0.86)
    assert result.pixels_per_unit == pytest.approx(10)
