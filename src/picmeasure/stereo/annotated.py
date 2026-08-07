"""Render annotated stereo images with matches and 3D length labels."""

from __future__ import annotations

import cv2
import numpy as np
import numpy.typing as npt

from picmeasure.stereo.models import StereoMeasurementFile

_PALETTE: tuple[tuple[int, int, int], ...] = (
    (50, 205, 50),
    (30, 144, 255),
    (255, 165, 0),
    (238, 130, 238),
    (220, 20, 60),
    (0, 206, 209),
    (255, 105, 180),
    (154, 205, 50),
)


def _bgr_from_index(idx: int) -> tuple[int, int, int]:
    rgb = _PALETTE[idx % len(_PALETTE)]
    return (int(rgb[2]), int(rgb[1]), int(rgb[0]))


def _draw_ball(
    canvas: npt.NDArray[np.uint8],
    center_xy: tuple[int, int] | None,
    radius_px: float | None,
    label: str,
) -> None:
    if center_xy is None or radius_px is None:
        return
    cx, cy = center_xy
    r = int(round(radius_px))
    color = (255, 255, 0)  # cyan in BGR
    cv2.circle(canvas, (cx, cy), r, color, 2, cv2.LINE_AA)
    cv2.putText(
        canvas,
        label,
        (cx - 80, cy - r - 10),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        color,
        2,
        cv2.LINE_AA,
    )


def render_stereo_annotated(
    left_bgr: npt.NDArray[np.uint8],
    right_bgr: npt.NDArray[np.uint8],
    sm: StereoMeasurementFile,
    output_path,
) -> None:
    """Create a side-by-side annotated image showing matches and lengths."""
    output_path = __import__("pathlib").Path(output_path)
    h = max(left_bgr.shape[0], right_bgr.shape[0])
    image_width = left_bgr.shape[1] + right_bgr.shape[1]
    w_total = image_width + 320
    canvas = np.full((h, w_total, 3), 255, dtype=np.uint8)

    canvas[: left_bgr.shape[0], : left_bgr.shape[1]] = left_bgr
    canvas[
        : right_bgr.shape[0],
        left_bgr.shape[1] : left_bgr.shape[1] + right_bgr.shape[1],
    ] = right_bgr
    offset_x = left_bgr.shape[1]

    # Draw reference balls.
    if sm.left_ball and sm.left_ball.detected:
        _draw_ball(
            canvas,
            sm.left_ball.ball_center_xy,
            sm.left_ball.ball_radius_px,
            "ref ball",
        )
    if sm.right_ball and sm.right_ball.detected:
        right_canvas = canvas[: right_bgr.shape[0], offset_x:]
        _draw_ball(
            right_canvas,
            sm.right_ball.ball_center_xy,
            sm.right_ball.ball_radius_px,
            "ref ball",
        )

    summary: list[str] = []
    # Draw branches and matches.
    for branch in sm.branches:
        color = _bgr_from_index(branch.branch_id - 1)
        pts_left = branch.vertices_left
        pts_right = branch.vertices_right

        for j in range(len(pts_left) - 1):
            cv2.line(canvas, pts_left[j], pts_left[j + 1], color, 1, cv2.LINE_AA)
        for j in range(len(pts_right) - 1):
            pr1 = (pts_right[j][0] + offset_x, pts_right[j][1])
            pr2 = (pts_right[j + 1][0] + offset_x, pts_right[j + 1][1])
            cv2.line(canvas, pr1, pr2, color, 1, cv2.LINE_AA)

        for (lx, ly), (rx, ry) in zip(pts_left, pts_right, strict=False):
            cv2.circle(canvas, (lx, ly), 4, color, 1, cv2.LINE_AA)
            cv2.circle(canvas, (rx + offset_x, ry), 4, color, 1, cv2.LINE_AA)

        if pts_left:
            summary.append(f"#{branch.branch_id} length: {branch.length_units:.2f} {branch.unit}")
        for diameter in branch.diameter_measurements:
            for edges, x_offset in ((diameter.edges_left, 0), (diameter.edges_right, offset_x)):
                p1 = (edges[0][0] + x_offset, edges[0][1])
                p2 = (edges[1][0] + x_offset, edges[1][1])
                cv2.line(canvas, p1, p2, color, 1, cv2.LINE_AA)
                cv2.drawMarker(canvas, p1, color, cv2.MARKER_CROSS, 7, 1, cv2.LINE_AA)
                cv2.drawMarker(canvas, p2, color, cv2.MARKER_CROSS, 7, 1, cv2.LINE_AA)
            summary.append(
                f"#{branch.branch_id} D{diameter.section_id}: "
                f"{diameter.diameter_units:.2f} {diameter.unit}"
            )

    cv2.putText(
        canvas,
        "Measurements",
        (image_width + 18, 35),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (30, 30, 30),
        2,
        cv2.LINE_AA,
    )
    for index, text in enumerate(summary):
        if 70 + index * 28 >= h:
            break
        cv2.putText(
            canvas,
            text,
            (image_width + 18, 70 + index * 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (50, 50, 50),
            1,
            cv2.LINE_AA,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), canvas)
