"""Shape-first reference-ball detector with optional color evidence.

Pipeline:
    1. BGR -> HSV.
    2. Detect circles in the grayscale image, independent of ball color.
    3. Also threshold orange-red regions and derive color/contour candidates.
    4. Rank candidates primarily by shape, with color coverage as a bonus.
    5. Return pixels_per_unit = 2 * radius_px / known_diameter_cm.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np
import numpy.typing as npt

from picmeasure.ball.models import BallCandidate, BallDetectionResult
from picmeasure.config import BallConfig

logger = logging.getLogger(__name__)


class BallDetector:
    """Detect a circular reference ball and derive the pixel/unit scale."""

    def __init__(self, config: BallConfig) -> None:
        self.config = config

    def detect(self, image: npt.NDArray[np.uint8]) -> BallDetectionResult:
        """Detect the ball in *image* (BGR).

        Returns a populated :class:`BallDetectionResult`. If no ball is found
        with sufficient confidence, ``detected`` is False and
        ``error_message`` describes why.
        """
        if image is None or image.size == 0:
            return BallDetectionResult(detected=False, error_message="empty image")

        candidates = self.detect_candidates(image)
        if not candidates:
            return BallDetectionResult(
                detected=False, error_message="no qualified circular reference-ball candidate"
            )
        candidate = candidates[0]
        cx, cy = candidate.center_xy
        r = candidate.radius_px
        confidence = candidate.score
        if confidence < self.config.min_confidence:
            return BallDetectionResult(
                detected=False,
                ball_center_xy=(cx, cy),
                ball_radius_px=r,
                confidence=confidence,
                error_message=(
                    f"confidence {confidence:.2f} below threshold "
                    f"{self.config.min_confidence:.2f} (method={candidate.method})"
                ),
            )

        pixels_per_cm = 2.0 * r / self.config.known_diameter_cm
        logger.info(
            "Ball detected via %s: center=(%d, %d) r=%.1fpx -> %.2f px/cm (conf=%.2f)",
            candidate.method,
            cx,
            cy,
            r,
            pixels_per_cm,
            confidence,
        )
        return BallDetectionResult(
            detected=True,
            pixels_per_unit=pixels_per_cm,
            ball_center_xy=(cx, cy),
            ball_radius_px=float(r),
            confidence=confidence,
            source="auto",
            candidate_score=confidence,
        )

    def detect_candidates(self, image: npt.NDArray[np.uint8]) -> list[BallCandidate]:
        """Return ranked, de-duplicated circular reference-ball regions."""
        if image is None or image.size == 0:
            return []
        mask = self._color_mask(image)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 1.2)
        mask_edges = cv2.Canny(mask, 50, 150)
        gray_edges = cv2.Canny(gray, 50, 150)
        gray_scale = min(1.0, 640.0 / max(gray.shape))
        gray_search = (
            cv2.resize(gray, None, fx=gray_scale, fy=gray_scale, interpolation=cv2.INTER_AREA)
            if gray_scale < 1.0
            else gray
        )

        raw: list[
            tuple[int, int, float, str, npt.NDArray[np.int32] | None, npt.NDArray[np.uint8]]
        ] = []
        for circle in self._hough_circles(
            gray_search,
            coordinate_scale=gray_scale,
            accumulator_threshold=max(30, self.config.hough_param2),
        ):
            raw.append((*circle, "gray_hough", None, gray_edges))
        for circle in self._hough_circles(mask):
            raw.append((*circle, "color_hough", None, mask_edges))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            area = float(cv2.contourArea(contour))
            if area <= 0:
                continue
            (x, y), radius = cv2.minEnclosingCircle(contour)
            if self.config.hough_min_radius <= radius <= self.config.hough_max_radius:
                raw.append(
                    (
                        int(round(x)),
                        int(round(y)),
                        float(radius),
                        "contour",
                        contour,
                        mask_edges,
                    )
                )

        candidates: list[BallCandidate] = []
        for cx, cy, radius, method, contour, edge_source in raw:
            candidate = self._score_candidate(mask, edge_source, cx, cy, radius, method, contour)
            if candidate.circularity < self.config.min_circularity:
                continue
            if candidate.edge_support < self.config.min_edge_support:
                continue
            if candidate.area_ratio < self.config.min_area_ratio:
                continue
            duplicate_index = next(
                (
                    index
                    for index, old in enumerate(candidates)
                    if np.hypot(cx - old.center_xy[0], cy - old.center_xy[1])
                    < max(radius, old.radius_px) * 0.5
                ),
                None,
            )
            if duplicate_index is None:
                candidates.append(candidate)
            elif candidate.score > candidates[duplicate_index].score or (
                candidate.method == "contour"
                and candidate.mask_fill >= 0.3
                and candidates[duplicate_index].method == "gray_hough"
            ):
                candidates[duplicate_index] = candidate
        radius_span = max(1.0, float(self.config.hough_max_radius - self.config.hough_min_radius))
        candidates.sort(
            key=lambda item: (
                0.75 * item.score
                + 0.75 * item.mask_fill
                + 0.3
                * min(
                    1.0,
                    (item.radius_px - self.config.hough_min_radius) / min(radius_span, 40.0),
                )
            ),
            reverse=True,
        )
        return candidates[: self.config.max_candidates]

    def _color_mask(self, image: npt.NDArray[np.uint8]) -> npt.NDArray[np.uint8]:
        """Build a binary mask of orange-red pixels in HSV space."""
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        cfg = self.config
        lower_low = np.array([0, cfg.hsv_sat_min, cfg.hsv_val_min], dtype=np.uint8)
        upper_low = np.array([cfg.hsv_hue_low_max, 255, 255], dtype=np.uint8)
        lower_high = np.array(
            [cfg.hsv_hue_high_min, cfg.hsv_sat_min, cfg.hsv_val_min], dtype=np.uint8
        )
        upper_high = np.array([179, 255, 255], dtype=np.uint8)

        mask = cv2.bitwise_or(
            cv2.inRange(hsv, lower_low, upper_low),
            cv2.inRange(hsv, lower_high, upper_high),
        )

        k = max(1, cfg.morph_kernel_size)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        return mask

    def _hough_circles(
        self,
        mask: npt.NDArray[np.uint8],
        *,
        coordinate_scale: float = 1.0,
        accumulator_threshold: int | None = None,
    ) -> list[tuple[int, int, float]]:
        """Return all Hough circle candidates."""
        cfg = self.config
        # Hough operates on a grayscale image with edges; the binary mask works
        # well because cv2.HoughCircles uses internal Canny on the input.
        circles = cv2.HoughCircles(
            mask,
            cv2.HOUGH_GRADIENT,
            dp=cfg.hough_dp,
            minDist=max(1, int(round(cfg.hough_min_dist * coordinate_scale))),
            param1=cfg.hough_param1,
            param2=accumulator_threshold or cfg.hough_param2,
            minRadius=max(1, int(round(cfg.hough_min_radius * coordinate_scale))),
            maxRadius=max(2, int(round(cfg.hough_max_radius * coordinate_scale))),
        )
        if circles is None:
            return []
        return [
            (
                int(round(float(x) / coordinate_scale)),
                int(round(float(y) / coordinate_scale)),
                float(r) / coordinate_scale,
            )
            for x, y, r in circles[0]
        ]

    def _score_candidate(
        self,
        mask: npt.NDArray[np.uint8],
        edge_source: npt.NDArray[np.uint8],
        cx: int,
        cy: int,
        radius: float,
        method: str,
        contour: npt.NDArray[np.int32] | None,
    ) -> BallCandidate:
        fill = min(1.0, self._mask_fill_ratio(mask, cx, cy, radius))
        if contour is None and method != "gray_hough":
            local = np.zeros_like(mask)
            cv2.circle(local, (cx, cy), int(round(radius * 1.2)), 255, -1)
            found, _ = cv2.findContours(
                cv2.bitwise_and(mask, local), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            contour = max(found, key=cv2.contourArea) if found else None
        circularity = 0.0
        area_ratio = 0.0
        if contour is not None:
            area = float(cv2.contourArea(contour))
            perimeter = float(cv2.arcLength(contour, True))
            circularity = min(1.0, 4.0 * np.pi * area / max(perimeter * perimeter, 1.0))
            area_ratio = min(1.0, area / max(np.pi * radius * radius, 1.0))
        elif method == "gray_hough":
            # The Hough accumulator itself supplies the circle-shape evidence.
            circularity = 1.0
            area_ratio = 1.0
        edge_support = self._edge_support(edge_source, cx, cy, radius)
        score = 0.15 * fill + 0.30 * circularity + 0.40 * edge_support + 0.15 * area_ratio
        return BallCandidate(
            (cx, cy), radius, float(score), fill, circularity, edge_support, area_ratio, method
        )

    @staticmethod
    def _edge_support(mask: npt.NDArray[np.uint8], cx: int, cy: int, radius: float) -> float:
        supported = 0
        samples = 72
        for angle in np.linspace(0, 2 * np.pi, samples, endpoint=False):
            x = int(round(cx + radius * np.cos(angle)))
            y = int(round(cy + radius * np.sin(angle)))
            x0, x1 = max(0, x - 1), min(mask.shape[1], x + 2)
            y0, y1 = max(0, y - 1), min(mask.shape[0], y + 2)
            supported += int(np.any(mask[y0:y1, x0:x1]))
        return supported / samples

    @staticmethod
    def _fallback_min_enclosing(
        mask: npt.NDArray[np.uint8],
    ) -> tuple[int, int, float] | None:
        """Fit a minimum enclosing circle to the largest connected component."""
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None
        largest = max(contours, key=cv2.contourArea)
        if cv2.contourArea(largest) <= 0:
            return None
        (x, y), r = cv2.minEnclosingCircle(largest)
        return int(round(x)), int(round(y)), float(r)

    @staticmethod
    def _mask_fill_ratio(mask: npt.NDArray[np.uint8], cx: int, cy: int, r: float) -> float:
        """Ratio of mask pixels inside the candidate circle to circle area."""
        if r <= 0:
            return 0.0
        h, w = mask.shape[:2]
        disk = np.zeros((h, w), dtype=np.uint8)
        cv2.circle(disk, (cx, cy), int(round(r)), 255, thickness=-1)
        inside = cv2.bitwise_and(mask, disk)
        circle_area = np.pi * r * r
        return float(np.count_nonzero(inside)) / max(circle_area, 1.0)

    def _estimate_confidence(
        self, mask: npt.NDArray[np.uint8], cx: int, cy: int, r: float
    ) -> float:
        """Confidence proxy: how much of the candidate disk is actually masked."""
        fill = self._mask_fill_ratio(mask, cx, cy, r)
        return float(min(1.0, max(0.0, fill)))
