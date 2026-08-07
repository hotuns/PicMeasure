"""Data models for reference-ball detection results."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BallCandidate:
    """One scored reference-ball candidate."""

    center_xy: tuple[int, int]
    radius_px: float
    score: float
    mask_fill: float
    circularity: float
    edge_support: float
    area_ratio: float
    method: str


@dataclass
class BallDetectionResult:
    """Output of the reference-ball detection stage.

    Shape-compatible with :class:`picmeasure.ruler.models.RulerDetectionResult`
    on the attributes consumed by downstream code (``detected``,
    ``pixels_per_unit``, ``tick_count``, ``confidence``,
    ``orientation_degrees``) so the same ``MeasurementSession.ruler_result``
    slot can hold either type without changing the exporter/annotator.

    Attributes:
        detected: Whether a reference ball was found.
        pixels_per_unit: Pixels per output unit (cm) derived from the ball's
            diameter; ``None`` if not detected.
        ball_center_xy: Detected ball center as ``(x, y)`` in image pixels.
        ball_radius_px: Detected ball radius in pixels.
        confidence: Confidence in [0.0, 1.0] proportional to the mask
            circularity / Hough accumulator strength.
        error_message: Human-readable error description when detection fails.
        tick_count: Always ``None`` for ball detection. Present for shape
            parity with ``RulerDetectionResult``.
        orientation_degrees: Always ``None`` for ball detection. Present for
            shape parity.
    """

    detected: bool
    pixels_per_unit: float | None = None
    ball_center_xy: tuple[int, int] | None = None
    ball_radius_px: float | None = None
    confidence: float | None = None
    error_message: str | None = None
    tick_count: int | None = None
    orientation_degrees: float | None = None
    source: str = "auto"
    candidate_score: float | None = None
