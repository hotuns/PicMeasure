"""Shared edge-assisted point selection primitives."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
import numpy.typing as npt

from picmeasure.config import PrecisionConfig

Point2D = tuple[int, int]


@dataclass
class PointPreview:
    """A raw click and its optionally snapped candidate."""

    raw: Point2D
    candidate: Point2D
    snapped: bool
    score: float = 0.0

    def nudge(self, dx: int, dy: int, image_shape: tuple[int, ...]) -> None:
        height, width = image_shape[:2]
        x = min(max(self.candidate[0] + dx, 0), width - 1)
        y = min(max(self.candidate[1] + dy, 0), height - 1)
        self.candidate = (x, y)
        self.snapped = False


def _gray(image: npt.NDArray[np.uint8]) -> npt.NDArray[np.uint8]:
    if image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def snap_to_edge(
    image: npt.NDArray[np.uint8],
    point: Point2D,
    config: PrecisionConfig,
) -> PointPreview:
    """Snap to the strongest local gradient, or retain the raw point."""
    gray = _gray(image)
    x, y = point
    radius = config.snap_radius_px
    x0, x1 = max(0, x - radius), min(gray.shape[1], x + radius + 1)
    y0, y1 = max(0, y - radius), min(gray.shape[0], y + radius + 1)
    if x1 - x0 < 3 or y1 - y0 < 3:
        return PointPreview(point, point, False)
    patch = gray[y0:y1, x0:x1]
    gx = cv2.Sobel(patch, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(patch, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = cv2.magnitude(gx, gy)
    iy, ix = np.unravel_index(int(np.argmax(magnitude)), magnitude.shape)
    score = float(magnitude[iy, ix])
    if score < config.min_edge_score:
        return PointPreview(point, point, False, score)
    return PointPreview(point, (x0 + int(ix), y0 + int(iy)), True, score)


def snap_to_centerline(
    image: npt.NDArray[np.uint8],
    point: Point2D,
    previous: Point2D | None,
    config: PrecisionConfig,
) -> PointPreview:
    """Find opposing edges normal to the previous segment and use their midpoint."""
    if previous is None or previous == point:
        return PointPreview(point, point, False)
    gray = _gray(image).astype(np.float32)
    dx, dy = point[0] - previous[0], point[1] - previous[1]
    norm = float(np.hypot(dx, dy))
    if norm < 1.0:
        return PointPreview(point, point, False)
    nx, ny = -dy / norm, dx / norm
    offsets = np.arange(-config.snap_radius_px, config.snap_radius_px + 1, dtype=np.float32)
    xs = np.clip(np.rint(point[0] + nx * offsets).astype(int), 0, gray.shape[1] - 1)
    ys = np.clip(np.rint(point[1] + ny * offsets).astype(int), 0, gray.shape[0] - 1)
    profile = gray[ys, xs]
    gradient = np.abs(np.gradient(profile))
    center = config.snap_radius_px
    left = gradient[:center]
    right = gradient[center + 1 :]
    if left.size == 0 or right.size == 0:
        return PointPreview(point, point, False)
    li = int(np.argmax(left))
    ri = center + 1 + int(np.argmax(right))
    score = float(min(gradient[li], gradient[ri]))
    if score < config.min_edge_score:
        return PointPreview(point, point, False, score)
    midpoint_offset = float(offsets[li] + offsets[ri]) / 2.0
    candidate = (
        int(round(point[0] + nx * midpoint_offset)),
        int(round(point[1] + ny * midpoint_offset)),
    )
    return PointPreview(point, candidate, True, score)


def magnifier_crop(
    image: npt.NDArray[np.uint8], point: Point2D, radius: int
) -> tuple[npt.NDArray[np.uint8], tuple[int, int]]:
    """Return a clipped local crop and its top-left image coordinate."""
    x, y = point
    x0, x1 = max(0, x - radius), min(image.shape[1], x + radius + 1)
    y0, y1 = max(0, y - radius), min(image.shape[0], y + radius + 1)
    return image[y0:y1, x0:x1], (x0, y0)
