"""Configuration management for picmeasure.

Algorithm parameters and behavioural settings live here, validated at
startup via pydantic. The project supports:

  * Reference-ball detection (calibration → pixels-per-cm).
  * Click-based polyline measurement (monocular).
  * Binocular stereo measurement with configurable extrinsics.

Anything beyond that (SAM segmentation, ruler detection, batch export
pipelines) was removed when the workflow was narrowed to "click and
measure".
"""

from __future__ import annotations

import logging
import math
import tomllib
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BallConfig(BaseModel):  # type: ignore[misc]
    """Controls orange-red reference ball detection.

    The ball's known physical diameter combined with its measured pixel
    diameter yields ``pixels_per_unit`` in the configured output unit.
    """

    known_diameter_cm: float = 4.0
    hsv_hue_low_max: int = 20
    hsv_hue_high_min: int = 165
    hsv_sat_min: int = 120
    hsv_val_min: int = 80
    morph_kernel_size: int = 5
    hough_dp: float = 1.2
    hough_min_dist: int = 50
    hough_param1: int = 100
    hough_param2: int = 20
    hough_min_radius: int = 8
    hough_max_radius: int = 200
    min_confidence: float = 0.3
    min_circularity: float = 0.30
    min_edge_support: float = 0.05
    min_area_ratio: float = 0.45
    max_candidates: int = 12

    @field_validator("known_diameter_cm")  # type: ignore[untyped-decorator]
    @classmethod
    def _validate_diameter(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("known_diameter_cm must be positive")
        return v

    @field_validator(  # type: ignore[untyped-decorator]
        "hsv_hue_low_max", "hsv_hue_high_min"
    )
    @classmethod
    def _validate_hue(cls, v: int) -> int:
        if not 0 <= v <= 179:
            raise ValueError("HSV hue must be in [0, 179] (OpenCV convention)")
        return v


class PrecisionConfig(BaseModel):  # type: ignore[misc]
    """Controls magnification and local edge-assisted point selection."""

    magnification: int = 8
    magnifier_radius_px: int = 16
    snap_radius_px: int = 12
    min_edge_score: float = 20.0

    @field_validator("magnification", "magnifier_radius_px", "snap_radius_px")  # type: ignore[untyped-decorator]
    @classmethod
    def _validate_positive_int(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("precision dimensions must be positive")
        return v

    @field_validator("min_edge_score")  # type: ignore[untyped-decorator]
    @classmethod
    def _validate_edge_score(cls, v: float) -> float:
        if v < 0:
            raise ValueError("min_edge_score must be non-negative")
        return v


class CorrespondenceConfig(BaseModel):  # type: ignore[misc]
    """Parameters for sparse NCC matching along rectified epipolar lines."""

    window_size: int = 31
    search_range_px: int = 1200
    uniqueness_ratio: float = 0.8
    gradient_weight: float = 0.35
    min_score: float = 0.35
    subpixel_refinement: bool = True

    @field_validator("window_size")  # type: ignore[untyped-decorator]
    @classmethod
    def _validate_window_size(cls, v: int) -> int:
        if v < 3 or v % 2 == 0:
            raise ValueError("window_size must be an odd integer >= 3")
        return v

    @field_validator("gradient_weight")  # type: ignore[untyped-decorator]
    @classmethod
    def _validate_gradient_weight(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("gradient_weight must be in [0, 1]")
        return v

    @field_validator("min_score")  # type: ignore[untyped-decorator]
    @classmethod
    def _validate_min_score(cls, v: float) -> float:
        if not -1.0 <= v <= 1.0:
            raise ValueError("min_score must be in [-1, 1]")
        return v


class CameraCalibrationConfig(BaseModel):  # type: ignore[misc]
    """Intrinsic calibration for one camera."""

    camera_matrix: list[list[float]]
    distortion_coefficients: list[float] = Field(default_factory=lambda: [0.0] * 5)
    rms_error: float | None = None

    @model_validator(mode="after")  # type: ignore[misc]
    def _validate_intrinsics(self) -> CameraCalibrationConfig:
        matrix = np.asarray(self.camera_matrix, dtype=np.float64)
        if matrix.shape != (3, 3):
            raise ValueError("camera_matrix must be 3x3")
        if matrix[0, 0] <= 0 or matrix[1, 1] <= 0:
            raise ValueError("camera focal lengths must be positive")
        if len(self.distortion_coefficients) < 4:
            raise ValueError("distortion_coefficients must contain at least 4 values")
        return self

    def matrix_array(self) -> np.ndarray:
        return np.asarray(self.camera_matrix, dtype=np.float64)

    def distortion_array(self) -> np.ndarray:
        return np.asarray(self.distortion_coefficients, dtype=np.float64)


class CalibrationQualityConfig(BaseModel):  # type: ignore[misc]
    """Persisted quality metrics from a stereo calibration run."""

    valid_pairs: int
    total_pairs: int
    stereo_rms_error: float
    rectified_median_vertical_error_px: float
    rectified_p90_vertical_error_px: float


class StereoConfig(BaseModel):  # type: ignore[misc]
    """Extrinsic/intrinsic calibration for a binocular stereo rig.

    The two cameras are assumed to have identical focal length and
    principal point. The rig is described by the rotation ``R`` and
    translation ``T`` from the left camera coordinate frame to the right
    camera coordinate frame.
    """

    enabled: bool = False
    image_size: tuple[int, int] | None = None
    left: CameraCalibrationConfig | None = None
    right: CameraCalibrationConfig | None = None
    quality: CalibrationQualityConfig | None = None
    focal_length_px: float | None = None
    principal_point: tuple[float, float] | None = None
    camera_matrix: list[list[float]] | None = None
    distortion_coefficients: list[float] = Field(default_factory=lambda: [0.0] * 5)
    rotation: list[list[float]] | None = None
    translation: list[float] | None = None
    baseline: float | None = None
    unit: Literal["mm", "cm"] = "cm"
    alpha: float = 0.0
    correspondence: CorrespondenceConfig = Field(default_factory=CorrespondenceConfig)

    @field_validator("focal_length_px")  # type: ignore[untyped-decorator]
    @classmethod
    def _validate_focal_length(cls, v: float | None) -> float | None:
        if v is not None and v <= 0:
            raise ValueError("focal_length_px must be positive")
        return v

    @field_validator("alpha")  # type: ignore[untyped-decorator]
    @classmethod
    def _validate_alpha(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("alpha must be in [0.0, 1.0]")
        return v

    @model_validator(mode="after")  # type: ignore[misc]
    def _validate_geometry(self) -> StereoConfig:
        """Ensure rotation is a valid SO(3) matrix and baseline matches |T|."""
        if self.rotation is not None:
            r = np.asarray(self.rotation, dtype=np.float64)
            if r.shape != (3, 3):
                raise ValueError("rotation must be a 3x3 matrix")
            identity = np.eye(3)
            if not np.allclose(r.T @ r, identity, atol=1e-4):
                raise ValueError("rotation matrix must be orthogonal (R^T R = I)")
            if not math.isclose(float(np.linalg.det(r)), 1.0, abs_tol=1e-4):
                raise ValueError("rotation matrix determinant must be +1")

        if self.translation is not None:
            t = np.asarray(self.translation, dtype=np.float64)
            if t.shape != (3,):
                raise ValueError("translation must be a 3-element vector")
            if np.linalg.norm(t) <= 0:
                raise ValueError("translation vector must be non-zero")
            if self.baseline is not None and self.baseline <= 0:
                raise ValueError("baseline must be positive")
            if self.baseline is not None:
                norm_t = float(np.linalg.norm(t))
                if not math.isclose(norm_t, self.baseline, rel_tol=0.01):
                    raise ValueError(
                        f"baseline ({self.baseline}) must equal |translation| "
                        f"({norm_t:.4f}) within 1%"
                    )

        if self.camera_matrix is not None:
            k = np.asarray(self.camera_matrix, dtype=np.float64)
            if k.shape != (3, 3):
                raise ValueError("camera_matrix must be 3x3")

        return self

    def camera_matrix_array(self, side: Literal["left", "right"] = "left") -> np.ndarray:
        """Return one camera matrix, falling back to the legacy shared intrinsics."""
        camera = self.left if side == "left" else self.right
        if camera is not None:
            return camera.matrix_array()
        if self.camera_matrix is not None:
            return np.asarray(self.camera_matrix, dtype=np.float64)
        if self.focal_length_px is None or self.principal_point is None:
            raise ValueError(
                "StereoConfig requires focal_length_px and principal_point, or camera_matrix"
            )
        fx = fy = float(self.focal_length_px)
        cx, cy = (float(v) for v in self.principal_point)
        return np.array([[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]], dtype=np.float64)

    def distortion_array(self, side: Literal["left", "right"] = "left") -> np.ndarray:
        """Return one distortion vector, with legacy shared coefficients as fallback."""
        camera = self.left if side == "left" else self.right
        if camera is not None:
            return camera.distortion_array()
        return np.asarray(self.distortion_coefficients, dtype=np.float64)

    def rotation_array(self) -> np.ndarray:
        """Return the 3x3 rotation matrix; default to identity if not set."""
        if self.rotation is None:
            return np.eye(3, dtype=np.float64)
        return np.asarray(self.rotation, dtype=np.float64)

    def translation_array(self) -> np.ndarray:
        """Return the 3-element translation vector."""
        if self.translation is None:
            raise ValueError("StereoConfig.translation is required")
        return np.asarray(self.translation, dtype=np.float64)

    @property
    def baseline_units(self) -> float:
        """Return the stereo baseline in the configured unit."""
        if self.baseline is not None:
            return float(self.baseline)
        return float(np.linalg.norm(self.translation_array()))


class LoggingConfig(BaseModel):  # type: ignore[misc]
    """Controls structured logging behaviour."""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


class AppConfig(BaseSettings):  # type: ignore[misc]
    """Top-level configuration loaded from TOML."""

    model_config = SettingsConfigDict(
        env_prefix="PICMEASURE_",
        env_nested_delimiter="__",
        extra="forbid",
    )

    output_unit: Literal["mm", "cm"] = "cm"
    image_formats: list[str] = Field(default_factory=lambda: ["jpg", "jpeg", "png", "tiff", "tif"])

    ball: BallConfig = Field(default_factory=BallConfig)
    precision: PrecisionConfig = Field(default_factory=PrecisionConfig)
    stereo: StereoConfig = Field(default_factory=StereoConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @classmethod
    def from_toml(cls, path: Path) -> AppConfig:
        """Load configuration from a TOML file."""
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return cls(**data)


def setup_logging(config: LoggingConfig) -> None:
    """Configure structured logging with the given level."""
    logging.basicConfig(
        level=getattr(logging, config.level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
