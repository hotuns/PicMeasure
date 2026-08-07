"""Chessboard-based intrinsic and stereo calibration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np
import numpy.typing as npt

from picmeasure.config import (
    CalibrationQualityConfig,
    CameraCalibrationConfig,
    StereoConfig,
)

ImageArray = npt.NDArray[np.uint8]
ImagePoints = npt.NDArray[np.float32]


@dataclass(frozen=True)
class BoardCalibrationResult:
    """A generated config plus pair-level detection diagnostics."""

    config: StereoConfig
    accepted_indices: list[int]
    rejected_indices: list[int]


@dataclass(frozen=True)
class _CalibrationSolution:
    k1: npt.NDArray[np.float64]
    d1: npt.NDArray[np.float64]
    left_rvecs: tuple[npt.NDArray[np.float64], ...]
    left_tvecs: tuple[npt.NDArray[np.float64], ...]
    k2: npt.NDArray[np.float64]
    d2: npt.NDArray[np.float64]
    right_rvecs: tuple[npt.NDArray[np.float64], ...]
    right_tvecs: tuple[npt.NDArray[np.float64], ...]
    stereo_rms: float
    rotation: npt.NDArray[np.float64]
    translation: npt.NDArray[np.float64]
    r1: npt.NDArray[np.float64]
    r2: npt.NDArray[np.float64]
    p1: npt.NDArray[np.float64]
    p2: npt.NDArray[np.float64]


def _object_points(columns: int, rows: int, square_size: float) -> npt.NDArray[np.float32]:
    points = np.zeros((columns * rows, 3), dtype=np.float32)
    points[:, :2] = np.mgrid[0:columns, 0:rows].T.reshape(-1, 2)
    points *= square_size
    return points


def _canonicalize_corner_order(corners: ImagePoints) -> ImagePoints:
    """Orient a symmetric chessboard consistently from image top-left."""
    ordered = np.asarray(corners, dtype=np.float32).reshape(-1, 2)
    if float(ordered[0].sum()) > float(ordered[-1].sum()):
        ordered = ordered[::-1].copy()
    return ordered


def _find_corners(image: ImageArray, pattern_size: tuple[int, int]) -> ImagePoints | None:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    found, corners = cv2.findChessboardCornersSB(
        gray,
        pattern_size,
        flags=cv2.CALIB_CB_NORMALIZE_IMAGE | cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY,
    )
    if found and corners is not None:
        return _canonicalize_corner_order(corners)

    found, corners = cv2.findChessboardCorners(
        gray,
        pattern_size,
        flags=cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE,
    )
    if not found or corners is None:
        return None
    refined = cv2.cornerSubPix(
        gray,
        corners,
        (11, 11),
        (-1, -1),
        (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001),
    )
    return _canonicalize_corner_order(refined)


def _mean_reprojection_error(
    object_points: list[npt.NDArray[np.float32]],
    image_points: list[ImagePoints],
    rvecs: tuple[npt.NDArray[np.float64], ...],
    tvecs: tuple[npt.NDArray[np.float64], ...],
    matrix: npt.NDArray[np.float64],
    distortion: npt.NDArray[np.float64],
) -> float:
    errors: list[float] = []
    for objects, observed, rotation, translation in zip(
        object_points, image_points, rvecs, tvecs, strict=True
    ):
        projected, _ = cv2.projectPoints(objects, rotation, translation, matrix, distortion)
        observed_xy = np.asarray(observed, dtype=np.float64).reshape(-1, 2)
        projected_xy = np.asarray(projected, dtype=np.float64).reshape(-1, 2)
        residuals = observed_xy - projected_xy
        errors.append(float(np.sqrt(np.mean(np.sum(residuals * residuals, axis=1)))))
    return float(np.mean(errors))


def _solve_calibration(
    object_points: list[npt.NDArray[np.float32]],
    left_points: list[ImagePoints],
    right_points: list[ImagePoints],
    image_size: tuple[int, int],
    known_baseline: float | None = None,
) -> _CalibrationSolution:
    _, k1, d1, left_rvecs, left_tvecs = cv2.calibrateCamera(
        object_points, left_points, image_size, None, None
    )
    _, k2, d2, right_rvecs, right_tvecs = cv2.calibrateCamera(
        object_points, right_points, image_size, None, None
    )
    stereo_rms, k1, d1, k2, d2, rotation, translation, _, _ = cv2.stereoCalibrate(
        object_points,
        left_points,
        right_points,
        k1,
        d1,
        k2,
        d2,
        image_size,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-6),
        flags=cv2.CALIB_FIX_INTRINSIC,
    )
    if known_baseline is not None:
        if known_baseline <= 0:
            raise ValueError("known_baseline must be positive")
        estimated_baseline = float(np.linalg.norm(translation))
        if estimated_baseline <= 1e-12:
            raise ValueError("calibration produced a zero translation")
        translation = translation * (known_baseline / estimated_baseline)
    r1, r2, p1, p2, _, _, _ = cv2.stereoRectify(
        k1,
        d1,
        k2,
        d2,
        image_size,
        rotation,
        translation,
        flags=cv2.CALIB_ZERO_DISPARITY,
        alpha=0.0,
    )
    return _CalibrationSolution(
        k1,
        d1,
        left_rvecs,
        left_tvecs,
        k2,
        d2,
        right_rvecs,
        right_tvecs,
        float(stereo_rms),
        rotation,
        translation,
        r1,
        r2,
        p1,
        p2,
    )


def _rectified_vertical_errors(
    solution: _CalibrationSolution,
    left_points: list[ImagePoints],
    right_points: list[ImagePoints],
) -> list[npt.NDArray[np.float32]]:
    errors: list[npt.NDArray[np.float32]] = []
    for left_corners, right_corners in zip(left_points, right_points, strict=True):
        rect_left = cv2.undistortPoints(
            left_corners.reshape(-1, 1, 2),
            solution.k1,
            solution.d1,
            R=solution.r1,
            P=solution.p1,
        )
        rect_right = cv2.undistortPoints(
            right_corners.reshape(-1, 1, 2),
            solution.k2,
            solution.d2,
            R=solution.r2,
            P=solution.p2,
        )
        errors.append(np.abs(rect_left[:, 0, 1] - rect_right[:, 0, 1]))
    return errors


def _inlier_pair_indices(pair_medians: list[float]) -> list[int]:
    """Keep pairs within a conservative multiple of the typical epipolar error."""
    typical = float(np.median(pair_medians))
    cutoff = max(2.0, typical * 3.0)
    return [index for index, error in enumerate(pair_medians) if error <= cutoff]


def calibrate_stereo_board(
    left_images: list[ImageArray],
    right_images: list[ImageArray],
    *,
    columns: int,
    rows: int,
    square_size: float,
    unit: Literal["mm", "cm"] = "mm",
    known_baseline: float | None = None,
    minimum_pairs: int = 6,
) -> BoardCalibrationResult:
    """Calibrate a rigid stereo rig from synchronized chessboard image pairs."""
    if len(left_images) != len(right_images):
        raise ValueError("left and right calibration image counts must match")
    if len(left_images) < minimum_pairs:
        raise ValueError(f"at least {minimum_pairs} stereo image pairs are required")
    if columns < 3 or rows < 3:
        raise ValueError("chessboard inner-corner columns and rows must be at least 3")
    if square_size <= 0:
        raise ValueError("square_size must be positive")
    if known_baseline is not None and known_baseline <= 0:
        raise ValueError("known_baseline must be positive")

    first_shape = left_images[0].shape[:2]
    if any(image.shape[:2] != first_shape for image in left_images + right_images):
        raise ValueError("all calibration images must use the same resolution")
    height, width = first_shape
    pattern_size = (columns, rows)
    board = _object_points(columns, rows, square_size)
    object_points: list[npt.NDArray[np.float32]] = []
    left_points: list[ImagePoints] = []
    right_points: list[ImagePoints] = []
    accepted: list[int] = []
    rejected: list[int] = []

    for index, (left, right) in enumerate(zip(left_images, right_images, strict=True)):
        left_corners = _find_corners(left, pattern_size)
        right_corners = _find_corners(right, pattern_size)
        if left_corners is None or right_corners is None:
            rejected.append(index)
            continue
        object_points.append(board.copy())
        left_points.append(left_corners)
        right_points.append(right_corners)
        accepted.append(index)

    if len(accepted) < minimum_pairs:
        raise ValueError(
            f"only {len(accepted)} valid chessboard pairs detected; {minimum_pairs} required"
        )

    image_size = (width, height)
    solution = _solve_calibration(
        object_points, left_points, right_points, image_size, known_baseline
    )
    vertical_errors = _rectified_vertical_errors(solution, left_points, right_points)
    inliers = _inlier_pair_indices([float(np.median(values)) for values in vertical_errors])
    if len(inliers) < len(object_points) and len(inliers) >= minimum_pairs:
        removed = [index for index in range(len(object_points)) if index not in inliers]
        rejected.extend(accepted[index] for index in removed)
        accepted = [accepted[index] for index in inliers]
        object_points = [object_points[index] for index in inliers]
        left_points = [left_points[index] for index in inliers]
        right_points = [right_points[index] for index in inliers]
        solution = _solve_calibration(
            object_points, left_points, right_points, image_size, known_baseline
        )
        vertical_errors = _rectified_vertical_errors(solution, left_points, right_points)
    rejected.sort()
    errors = np.concatenate(vertical_errors)

    quality = CalibrationQualityConfig(
        valid_pairs=len(accepted),
        total_pairs=len(left_images),
        stereo_rms_error=solution.stereo_rms,
        rectified_median_vertical_error_px=float(np.median(errors)),
        rectified_p90_vertical_error_px=float(np.percentile(errors, 90)),
    )
    config = StereoConfig(
        enabled=True,
        image_size=image_size,
        left=CameraCalibrationConfig(
            camera_matrix=solution.k1.tolist(),
            distortion_coefficients=solution.d1.reshape(-1).tolist(),
            rms_error=_mean_reprojection_error(
                object_points,
                left_points,
                solution.left_rvecs,
                solution.left_tvecs,
                solution.k1,
                solution.d1,
            ),
        ),
        right=CameraCalibrationConfig(
            camera_matrix=solution.k2.tolist(),
            distortion_coefficients=solution.d2.reshape(-1).tolist(),
            rms_error=_mean_reprojection_error(
                object_points,
                right_points,
                solution.right_rvecs,
                solution.right_tvecs,
                solution.k2,
                solution.d2,
            ),
        ),
        rotation=solution.rotation.tolist(),
        translation=solution.translation.reshape(-1).tolist(),
        baseline=float(np.linalg.norm(solution.translation)),
        unit=unit,
        alpha=0.0,
        quality=quality,
    )
    return BoardCalibrationResult(config, accepted, rejected)


def stereo_config_to_toml(config: StereoConfig) -> str:
    """Serialize a complete stereo calibration to a human-readable TOML file."""
    if config.left is None or config.right is None or config.image_size is None:
        raise ValueError("complete left/right calibration is required for export")

    def vector(values: list[float]) -> str:
        return "[" + ", ".join(f"{value:.12g}" for value in values) + "]"

    def matrix(values: list[list[float]]) -> str:
        rows = ",\n  ".join(vector(row) for row in values)
        return "[\n  " + rows + "\n]"

    quality = config.quality
    lines = [
        "[stereo]",
        "enabled = true",
        f"image_size = [{config.image_size[0]}, {config.image_size[1]}]",
        f'unit = "{config.unit}"',
        f"baseline = {config.baseline_units:.12g}",
        f"alpha = {config.alpha:.12g}",
        f"rotation = {matrix(config.rotation or [])}",
        f"translation = {vector(config.translation or [])}",
        "",
        "[stereo.left]",
        f"camera_matrix = {matrix(config.left.camera_matrix)}",
        f"distortion_coefficients = {vector(config.left.distortion_coefficients)}",
        f"rms_error = {config.left.rms_error or 0.0:.12g}",
        "",
        "[stereo.right]",
        f"camera_matrix = {matrix(config.right.camera_matrix)}",
        f"distortion_coefficients = {vector(config.right.distortion_coefficients)}",
        f"rms_error = {config.right.rms_error or 0.0:.12g}",
    ]
    if quality is not None:
        lines.extend(
            [
                "",
                "[stereo.quality]",
                f"valid_pairs = {quality.valid_pairs}",
                f"total_pairs = {quality.total_pairs}",
                f"stereo_rms_error = {quality.stereo_rms_error:.12g}",
                "rectified_median_vertical_error_px = "
                f"{quality.rectified_median_vertical_error_px:.12g}",
                f"rectified_p90_vertical_error_px = {quality.rectified_p90_vertical_error_px:.12g}",
            ]
        )
    return "\n".join(lines) + "\n"
