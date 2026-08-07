"""Reference ball detection package.

Detects an orange-red ball of known diameter in an image. The ball's pixel
radius establishes ``pixels_per_unit`` (px/cm) for downstream measurement.
"""

from picmeasure.ball.detector import BallDetector
from picmeasure.ball.models import BallDetectionResult

__all__ = ["BallDetector", "BallDetectionResult"]
