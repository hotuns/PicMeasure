"""Data models for binocular stereo measurement."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
import numpy.typing as npt

from picmeasure.ball.models import BallDetectionResult

if TYPE_CHECKING:
    from picmeasure.stereo.geometry import Point3D


@dataclass(frozen=True)
class StereoCalibration:
    """Intrinsic/extrinsic calibration of a rectifiable stereo rig.

    All arrays are stored as numpy float64 arrays in the OpenCV convention:
    ``K``/``D`` are the left intrinsics, ``K2``/``D2`` are the right
    intrinsics, ``R``/``T`` describe the right camera relative to the left
    camera, and ``image_size`` is (width, height).
    """

    k: npt.NDArray[np.float64]
    d: npt.NDArray[np.float64]
    k2: npt.NDArray[np.float64]
    d2: npt.NDArray[np.float64]
    r: npt.NDArray[np.float64]
    t: npt.NDArray[np.float64]
    image_size: tuple[int, int]
    baseline_units: float
    unit: str = "cm"
    alpha: float = 0.0

    def __post_init__(self) -> None:
        # Force float64 and validate shapes.
        object.__setattr__(self, "k", np.asarray(self.k, dtype=np.float64).reshape(3, 3))
        object.__setattr__(self, "d", np.asarray(self.d, dtype=np.float64).reshape(-1))
        object.__setattr__(self, "k2", np.asarray(self.k2, dtype=np.float64).reshape(3, 3))
        object.__setattr__(self, "d2", np.asarray(self.d2, dtype=np.float64).reshape(-1))
        object.__setattr__(self, "r", np.asarray(self.r, dtype=np.float64).reshape(3, 3))
        object.__setattr__(self, "t", np.asarray(self.t, dtype=np.float64).reshape(3))


@dataclass(frozen=True)
class RectificationMaps:
    """Outputs of ``cv2.stereoRectify`` and ``cv2.initUndistortRectifyMap``."""

    r1: npt.NDArray[np.float64]
    r2: npt.NDArray[np.float64]
    p1: npt.NDArray[np.float64]
    p2: npt.NDArray[np.float64]
    q: npt.NDArray[np.float64]
    map1x: npt.NDArray[np.float64]
    map1y: npt.NDArray[np.float64]
    map2x: npt.NDArray[np.float64]
    map2y: npt.NDArray[np.float64]
    roi1: tuple[int, int, int, int]
    roi2: tuple[int, int, int, int]


@dataclass(frozen=True)
class StereoMatch:
    """A matched 2D point pair with quality metadata."""

    left_pt: tuple[float, float]
    right_pt: tuple[float, float]
    score: float
    manual: bool = False


@dataclass
class StereoDiameterMeasurement:
    """One stereo branch cross-section reconstructed from two edge points."""

    section_id: int
    edges_left: tuple[tuple[int, int], tuple[int, int]]
    edges_right: tuple[tuple[int, int], tuple[int, int]]
    edges_3d: tuple[Point3D, Point3D]
    diameter_units: float
    unit: str = "cm"


@dataclass
class StereoBranch:
    """One measured branch with left/right/3D vertices and length."""

    branch_id: int
    vertices_left: list[tuple[int, int]] = field(default_factory=list)
    vertices_right: list[tuple[int, int]] = field(default_factory=list)
    vertices_3d: list[Point3D] = field(default_factory=list)
    length_units: float = 0.0
    unit: str = "cm"
    diameter_measurements: list[StereoDiameterMeasurement] = field(default_factory=list)


@dataclass
class StereoMeasurementFile:
    """Top-level stereo measurement container."""

    left_image_path: str
    right_image_path: str
    unit: str
    baseline_units: float
    focal_length_px: float
    principal_point: tuple[float, float]
    rotation: list[list[float]]
    translation: list[float]
    distortion_coefficients: list[float]
    reprojection_error_px: float | None = None
    left_ball: BallDetectionResult | None = None
    right_ball: BallDetectionResult | None = None
    triangulated_ball_diameter_units: float | None = None
    branches: list[StereoBranch] = field(default_factory=list)

    def scale_check_ok(self, expected_diameter: float, tolerance: float = 0.1) -> bool:
        """Return True if the triangulated ball diameter matches the expected diameter."""
        if self.triangulated_ball_diameter_units is None:
            return False
        return (
            abs(self.triangulated_ball_diameter_units - expected_diameter) / expected_diameter
            <= tolerance
        )


@dataclass
class CalibrationReport:
    """Serializable report produced by ``stereo-calibrate``."""

    rectified: bool
    image_size: tuple[int, int]
    baseline_units: float
    baseline_unit: str
    focal_length_px: float
    principal_point: tuple[float, float]
    left_ball: BallDetectionResult | None = None
    right_ball: BallDetectionResult | None = None
    triangulated_ball_diameter_units: float | None = None
    reprojection_error_px: float | None = None
    message: str | None = None

    def to_dict(self) -> dict:
        """Serialize to a JSON-friendly dictionary."""

        def _ball_dict(b: BallDetectionResult | None) -> dict | None:
            if b is None:
                return None
            return {
                "detected": b.detected,
                "pixels_per_unit": b.pixels_per_unit,
                "ball_center_xy": list(b.ball_center_xy) if b.ball_center_xy else None,
                "ball_radius_px": b.ball_radius_px,
                "confidence": b.confidence,
                "error_message": b.error_message,
            }

        return {
            "rectified": self.rectified,
            "image_size": list(self.image_size),
            "baseline_units": self.baseline_units,
            "baseline_unit": self.baseline_unit,
            "focal_length_px": self.focal_length_px,
            "principal_point": list(self.principal_point),
            "left_ball": _ball_dict(self.left_ball),
            "right_ball": _ball_dict(self.right_ball),
            "triangulated_ball_diameter_units": self.triangulated_ball_diameter_units,
            "reprojection_error_px": self.reprojection_error_px,
            "message": self.message,
        }
