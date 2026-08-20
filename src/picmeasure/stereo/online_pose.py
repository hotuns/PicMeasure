"""Refine stereo extrinsics from features in the current image pair."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
import numpy.typing as npt

from picmeasure.stereo.calibration import build_rectification
from picmeasure.stereo.models import RectificationMaps, StereoCalibration

ImageArray = npt.NDArray[np.uint8]


@dataclass(frozen=True)
class OnlinePoseResult:
    """Rectification selected after comparing configured and online poses."""

    calibration: StereoCalibration
    maps: RectificationMaps
    source: str
    match_count: int
    inlier_count: int
    median_vertical_error_px: float
    p90_vertical_error_px: float


def _configured_pose_is_usable(errors: tuple[float, float]) -> bool:
    return errors[0] <= 2.0 and errors[1] <= 5.0


def _online_pose_is_usable(errors: tuple[float, float]) -> bool:
    return errors[0] <= 2.0 and errors[1] <= 4.0


def _skew(vector: np.ndarray) -> np.ndarray:
    x, y, z = vector
    return np.asarray([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]])


def _constrained_rotation(
    normalized_left: np.ndarray,
    normalized_right: np.ndarray,
    configured: StereoCalibration,
) -> tuple[np.ndarray, np.ndarray]:
    """Fit current three-axis rotation while preserving calibrated translation."""
    left_h = np.column_stack((normalized_left, np.ones(len(normalized_left))))
    right_h = np.column_stack((normalized_right, np.ones(len(normalized_right))))
    translation = configured.t / np.linalg.norm(configured.t)
    translation_cross = _skew(translation)
    correction = np.zeros(3, dtype=np.float64)
    max_correction = np.radians(8.0)

    def residual(parameters: np.ndarray) -> np.ndarray:
        rotation = cv2.Rodrigues(parameters)[0] @ configured.r
        essential = translation_cross @ rotation
        essential_left = (essential @ left_h.T).T
        essential_t_right = (essential.T @ right_h.T).T
        denominator = np.sqrt(
            essential_left[:, 0] ** 2
            + essential_left[:, 1] ** 2
            + essential_t_right[:, 0] ** 2
            + essential_t_right[:, 1] ** 2
        )
        numerator = np.sum(right_h * essential_left, axis=1)
        return numerator / np.maximum(denominator, 1e-12)

    for _ in range(30):
        errors = residual(correction)
        median = float(np.median(errors))
        scale = 1.4826 * float(np.median(np.abs(errors - median))) + 1e-9
        weights = np.minimum(1.0, 2.5 * scale / (np.abs(errors - median) + 1e-12))
        epsilon = 1e-6
        jacobian = np.column_stack(
            [
                (residual(correction + np.eye(3)[axis] * epsilon) - errors) / epsilon
                for axis in range(3)
            ]
        )
        step = np.linalg.lstsq(
            jacobian * weights[:, None], -errors * weights, rcond=None
        )[0]
        if np.linalg.norm(step) > 0.005:
            step *= 0.005 / np.linalg.norm(step)
        updated = correction + step
        if np.linalg.norm(updated) > max_correction:
            updated *= max_correction / np.linalg.norm(updated)
        if np.linalg.norm(updated - correction) < 1e-9:
            break
        correction = updated

    return cv2.Rodrigues(correction)[0] @ configured.r, correction


def _feature_points(left: ImageArray, right: ImageArray) -> tuple[np.ndarray, np.ndarray]:
    gray_left = cv2.cvtColor(left, cv2.COLOR_BGR2GRAY)
    gray_right = cv2.cvtColor(right, cv2.COLOR_BGR2GRAY)
    detector = cv2.SIFT_create(nfeatures=8000)
    key_left, descriptors_left = detector.detectAndCompute(gray_left, None)
    key_right, descriptors_right = detector.detectAndCompute(gray_right, None)
    if descriptors_left is None or descriptors_right is None:
        raise ValueError("当前图片缺少可用于双目对齐的特征")
    pairs = cv2.BFMatcher(cv2.NORM_L2).knnMatch(descriptors_left, descriptors_right, k=2)
    matches = [best for best, second in pairs if best.distance < 0.72 * second.distance]
    if len(matches) < 30:
        raise ValueError(f"当前图片只有 {len(matches)} 个可靠特征匹配，至少需要 30 个")
    points_left = np.asarray(
        [key_left[match.queryIdx].pt for match in matches], dtype=np.float64
    )
    points_right = np.asarray(
        [key_right[match.trainIdx].pt for match in matches], dtype=np.float64
    )
    return points_left, points_right


def _vertical_errors(
    calibration: StereoCalibration,
    maps: RectificationMaps,
    points_left: np.ndarray,
    points_right: np.ndarray,
    mask: np.ndarray,
) -> tuple[float, float]:
    rect_left = cv2.undistortPoints(
        points_left.reshape(-1, 1, 2), calibration.k, calibration.d, R=maps.r1, P=maps.p1
    ).reshape(-1, 2)
    rect_right = cv2.undistortPoints(
        points_right.reshape(-1, 1, 2), calibration.k2, calibration.d2, R=maps.r2, P=maps.p2
    ).reshape(-1, 2)
    errors = np.abs(rect_left[mask, 1] - rect_right[mask, 1])
    return float(np.median(errors)), float(np.percentile(errors, 90))


def refine_rectification(
    left: ImageArray,
    right: ImageArray,
    configured: StereoCalibration,
) -> OnlinePoseResult:
    """Select configured or feature-estimated extrinsics for this image pair."""
    points_left, points_right = _feature_points(left, right)
    _, fundamental_mask = cv2.findFundamentalMat(
        points_left, points_right, cv2.FM_RANSAC, 1.5, 0.999
    )
    if fundamental_mask is None or int(np.count_nonzero(fundamental_mask)) < 25:
        raise ValueError("当前图片缺少稳定的双目几何特征")
    geometry_valid = fundamental_mask.ravel() > 0
    valid_left = points_left[geometry_valid]
    valid_right = points_right[geometry_valid]
    normalized_left = cv2.undistortPoints(
        valid_left.reshape(-1, 1, 2), configured.k, configured.d
    ).reshape(-1, 2)
    normalized_right = cv2.undistortPoints(
        valid_right.reshape(-1, 1, 2), configured.k2, configured.d2
    ).reshape(-1, 2)
    configured_maps = build_rectification(configured)
    configured_error = _vertical_errors(
        configured, configured_maps, points_left, points_right, geometry_valid
    )
    rotation, _ = _constrained_rotation(normalized_left, normalized_right, configured)
    estimated = StereoCalibration(
        k=configured.k,
        d=configured.d,
        k2=configured.k2,
        d2=configured.d2,
        r=rotation,
        t=configured.t,
        image_size=configured.image_size,
        baseline_units=configured.baseline_units,
        unit=configured.unit,
        alpha=configured.alpha,
    )
    estimated_maps = build_rectification(estimated)
    estimated_error = _vertical_errors(
        estimated, estimated_maps, points_left, points_right, geometry_valid
    )
    inlier_count = int(np.count_nonzero(geometry_valid))
    if estimated_error[1] + 0.5 < configured_error[1] and _online_pose_is_usable(
        estimated_error
    ):
        return OnlinePoseResult(
            estimated,
            estimated_maps,
            "features",
            len(points_left),
            int(inlier_count),
            estimated_error[0],
            estimated_error[1],
        )
    if _configured_pose_is_usable(configured_error):
        return OnlinePoseResult(
            configured,
            configured_maps,
            "configured",
            len(points_left),
            int(inlier_count),
            configured_error[0],
            configured_error[1],
        )
    raise ValueError(
        "在线姿态与配置外参都无法将对应点校正到同一水平线，"
        f"当前最小 P90 误差为 {min(configured_error[1], estimated_error[1]):.2f} px"
    )
