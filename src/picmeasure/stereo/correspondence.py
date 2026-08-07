"""Sparse correspondence search along rectified epipolar lines."""

from __future__ import annotations

import logging

import cv2
import numpy as np
import numpy.typing as npt

from picmeasure.config import CorrespondenceConfig
from picmeasure.stereo.models import StereoMatch

logger = logging.getLogger(__name__)


def _ensure_grayscale(image: npt.NDArray[np.uint8]) -> npt.NDArray[np.uint8]:
    if len(image.shape) == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return image


def _gradient_magnitude(image: npt.NDArray[np.uint8]) -> npt.NDArray[np.float32]:
    """Return a scale-stable Sobel magnitude image for edge-aware matching."""
    gray = _ensure_grayscale(image)
    gray_float = gray.astype(np.float32, copy=False)
    grad_x = cv2.Sobel(gray_float, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray_float, cv2.CV_32F, 0, 1, ksize=3)
    return cv2.magnitude(grad_x, grad_y)


def _subpixel_peak(scores: npt.NDArray[np.float64], best_idx: int) -> float:
    """Parabola fit around the best integer index for subpixel refinement."""
    if best_idx == 0 or best_idx == len(scores) - 1:
        return float(best_idx)
    y_m1 = float(scores[best_idx - 1])
    y_0 = float(scores[best_idx])
    y_p1 = float(scores[best_idx + 1])
    denom = y_m1 - 2.0 * y_0 + y_p1
    if abs(denom) < 1e-9:
        return float(best_idx)
    delta = 0.5 * (y_m1 - y_p1) / denom
    return float(best_idx) + delta


def match_along_epipolar_line(
    rect_left: npt.NDArray[np.uint8],
    rect_right: npt.NDArray[np.uint8],
    left_pt: tuple[float, float],
    cfg: CorrespondenceConfig,
) -> StereoMatch:
    """Find the corresponding point in the right image for a left-image point.

    The input images are assumed already rectified so that epipolar lines are
    horizontal. The function extracts a small template around ``left_pt`` in
    the left image and slides it along the same scanline in the right image
    within ``search_range_px``. The peak NCC response is returned, with an
    optional uniqueness ratio check.

    Args:
        rect_left: Rectified left image (BGR or grayscale).
        rect_right: Rectified right image (BGR or grayscale).
        left_pt: (x, y) in the left image.
        cfg: Correspondence parameters.

    Returns:
        ``StereoMatch`` containing the right-image coordinate and the NCC score.

    Raises:
        RuntimeError: If the point is too close to the image border or no
            acceptable match is found.
    """
    left_gray = _ensure_grayscale(rect_left)
    right_gray = _ensure_grayscale(rect_right)
    left_gradient = _gradient_magnitude(rect_left)
    right_gradient = _gradient_magnitude(rect_right)

    h, w = left_gray.shape[:2]
    half_w = cfg.window_size // 2

    xl_f, yl_f = left_pt
    xl = int(round(xl_f))
    yl = int(round(yl_f))

    if not (half_w <= xl < w - half_w and half_w <= yl < h - half_w):
        raise RuntimeError(
            f"left point ({xl}, {yl}) is too close to the image border for a "
            f"{cfg.window_size}x{cfg.window_size} matching window"
        )

    template = left_gray[yl - half_w : yl + half_w + 1, xl - half_w : xl + half_w + 1]
    gradient_template = left_gradient[
        yl - half_w : yl + half_w + 1, xl - half_w : xl + half_w + 1
    ]
    if float(np.std(template)) < 1e-6 and float(np.std(gradient_template)) < 1e-6:
        raise RuntimeError("matching window has insufficient texture")

    # Search along the same scanline in the right image.
    # Disparity is positive: x_r = x_l - d, with d > 0 for a forward-facing rig.
    min_xr = max(half_w, xl - cfg.search_range_px)
    max_xr = min(w - half_w - 1, xl + 1)

    if max_xr - min_xr < cfg.window_size:
        raise RuntimeError("search range too small or point too close to right border")

    search_strip = right_gray[
        yl - half_w : yl + half_w + 1,
        min_xr - half_w : max_xr + half_w + 1,
    ]
    gradient_strip = right_gradient[
        yl - half_w : yl + half_w + 1,
        min_xr - half_w : max_xr + half_w + 1,
    ]
    gray_scores = np.asarray(
        cv2.matchTemplate(search_strip, template, cv2.TM_CCOEFF_NORMED).reshape(-1),
        dtype=np.float64,
    )
    gradient_scores = np.asarray(
        cv2.matchTemplate(gradient_strip, gradient_template, cv2.TM_CCOEFF_NORMED).reshape(-1),
        dtype=np.float64,
    )
    if float(np.std(gradient_template)) < 1e-6:
        gradient_scores = gray_scores.copy()
    gradient_weight = cfg.gradient_weight
    scores_arr = (1.0 - gradient_weight) * gray_scores + gradient_weight * gradient_scores
    if not np.all(np.isfinite(scores_arr)):
        raise RuntimeError("matching window has insufficient texture")
    best_local = int(np.argmax(scores_arr))
    best_score = float(scores_arr[best_local])
    if best_score < cfg.min_score:
        raise RuntimeError(
            f"insufficient matching texture: best correlation is {best_score:.3f}"
        )

    # Ignore the main peak's immediate neighborhood when measuring ambiguity.
    if len(scores_arr) > cfg.window_size:
        alternatives = scores_arr.copy()
        exclusion = cfg.window_size
        alternatives[
            max(0, best_local - exclusion) : min(len(alternatives), best_local + exclusion + 1)
        ] = -np.inf
        second_best = float(np.max(alternatives))
        if best_score <= 0:
            raise RuntimeError(
                f"insufficient matching texture: best correlation is {best_score:.3f}"
            )
        ambiguity_ratio = second_best / best_score
        if ambiguity_ratio > cfg.uniqueness_ratio:
            raise RuntimeError(
                f"match is not unique enough: best={best_score:.3f}, "
                f"second={second_best:.3f}, ratio={ambiguity_ratio:.3f}"
            )

    if cfg.subpixel_refinement and 0 < best_local < len(scores_arr) - 1:
        refined_offset = _subpixel_peak(scores_arr, best_local)
        xr_best = min_xr + refined_offset
    else:
        xr_best = float(min_xr + best_local)

    logger.debug(
        "Matched left=(%.1f, %.1f) to right=(%.2f, %.1f), score=%.3f",
        xl_f,
        yl_f,
        xr_best,
        float(yl),
        best_score,
    )

    return StereoMatch(
        left_pt=(xl_f, yl_f),
        right_pt=(xr_best, float(yl)),
        score=best_score,
        manual=False,
    )
