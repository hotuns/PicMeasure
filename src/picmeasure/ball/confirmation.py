"""Interactive confirmation for automatic or manually defined reference balls."""

from __future__ import annotations

import math

import cv2
import matplotlib.pyplot as plt
import numpy.typing as npt
from matplotlib.patches import Circle
from matplotlib.widgets import Button

from picmeasure.ball.detector import BallDetector
from picmeasure.ball.models import BallCandidate, BallDetectionResult
from picmeasure.config import BallConfig, PrecisionConfig
from picmeasure.precision import magnifier_crop


def result_from_candidate(candidate: BallCandidate, config: BallConfig) -> BallDetectionResult:
    """Convert a user-confirmed candidate to the public calibration result."""
    return BallDetectionResult(
        detected=True,
        pixels_per_unit=2.0 * candidate.radius_px / config.known_diameter_cm,
        ball_center_xy=candidate.center_xy,
        ball_radius_px=candidate.radius_px,
        confidence=candidate.score,
        source="auto",
        candidate_score=candidate.score,
    )


def manual_ball_result(
    center: tuple[int, int], edge: tuple[int, int], config: BallConfig
) -> BallDetectionResult:
    """Build a calibration from a manually confirmed center and edge."""
    radius = math.hypot(edge[0] - center[0], edge[1] - center[1])
    if radius <= 0:
        raise ValueError("reference-ball radius must be positive")
    return BallDetectionResult(
        detected=True,
        pixels_per_unit=2.0 * radius / config.known_diameter_cm,
        ball_center_xy=center,
        ball_radius_px=radius,
        confidence=1.0,
        source="manual",
    )


def confirm_reference_ball(
    image_bgr: npt.NDArray,
    ball_config: BallConfig,
    precision_config: PrecisionConfig,
    *,
    allow_skip: bool = False,
) -> BallDetectionResult | None:
    """Show ranked candidates and require explicit confirm, manual entry, or skip."""
    candidates = BallDetector(ball_config).detect_candidates(image_bgr)
    state: dict[str, object] = {"index": 0, "manual": False, "points": [], "result": None}
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    fig = plt.figure(figsize=(12, 8))
    ax = fig.add_axes([0.04, 0.18, 0.72, 0.78])
    ax.imshow(rgb)
    zoom_ax = fig.add_axes([0.79, 0.48, 0.19, 0.42])
    status = fig.text(0.79, 0.40, "", fontsize=10, va="top")
    artists: list[object] = []

    def redraw() -> None:
        for artist in artists:
            artist.remove()  # type: ignore[attr-defined]
        artists.clear()
        if candidates and not state["manual"]:
            index = int(state["index"])
            for i, candidate in enumerate(candidates):
                patch = Circle(
                    candidate.center_xy,
                    candidate.radius_px,
                    fill=False,
                    edgecolor="cyan" if i == index else "yellow",
                    linewidth=2.0 if i == index else 0.8,
                    alpha=1.0 if i == index else 0.45,
                )
                ax.add_patch(patch)
                artists.append(patch)
            candidate = candidates[index]
            status.set_text(
                f"候选 {index + 1}/{len(candidates)}\n总分 {candidate.score:.2f}\n"
                f"圆度 {candidate.circularity:.2f}\n边缘 {candidate.edge_support:.2f}\n"
                f"填充 {candidate.mask_fill:.2f}\nEnter=确认  ←/→=切换"
            )
        elif state["manual"]:
            points = state["points"]
            status.set_text("手动校准：" + ("点击圆心" if not points else "点击圆周边缘"))
        else:
            status.set_text("未找到可靠候选，请选择手动校准")
        fig.canvas.draw_idle()

    def finish(result: BallDetectionResult | None) -> None:
        state["result"] = result
        plt.close(fig)

    def on_click(event: object) -> None:
        if not state["manual"] or getattr(event, "inaxes", None) != ax:
            return
        xdata, ydata = getattr(event, "xdata", None), getattr(event, "ydata", None)
        if xdata is None or ydata is None:
            return
        points = state["points"]
        points.append((int(round(xdata)), int(round(ydata))))  # type: ignore[union-attr]
        if len(points) == 2:  # type: ignore[arg-type]
            finish(manual_ball_result(points[0], points[1], ball_config))  # type: ignore[index]
        redraw()

    def on_move(event: object) -> None:
        if getattr(event, "inaxes", None) != ax:
            return
        xdata, ydata = getattr(event, "xdata", None), getattr(event, "ydata", None)
        if xdata is None or ydata is None:
            return
        crop, _ = magnifier_crop(
            rgb, (int(round(xdata)), int(round(ydata))), precision_config.magnifier_radius_px
        )
        zoom_ax.clear()
        zoom_ax.imshow(crop, interpolation="nearest")
        zoom_ax.axhline((crop.shape[0] - 1) / 2, color="cyan", linewidth=0.7)
        zoom_ax.axvline((crop.shape[1] - 1) / 2, color="cyan", linewidth=0.7)
        zoom_ax.set_xticks([])
        zoom_ax.set_yticks([])
        fig.canvas.draw_idle()

    def on_key(event: object) -> None:
        key = (getattr(event, "key", "") or "").lower()
        if key in ("right", "left") and candidates and not state["manual"]:
            delta = 1 if key == "right" else -1
            state["index"] = (int(state["index"]) + delta) % len(candidates)
            redraw()
        elif key in ("enter", "return") and candidates and not state["manual"]:
            finish(result_from_candidate(candidates[int(state["index"])], ball_config))
        elif key == "escape" and allow_skip:
            finish(None)

    axes = [fig.add_axes([0.04 + i * 0.15, 0.05, 0.13, 0.07]) for i in range(4)]
    buttons = [
        Button(axes[0], "上一个"),
        Button(axes[1], "下一个"),
        Button(axes[2], "确认"),
        Button(axes[3], "手动"),
    ]
    buttons[0].on_clicked(
        lambda _: (
            state.__setitem__("index", (int(state["index"]) - 1) % max(len(candidates), 1)),
            redraw(),
        )
    )
    buttons[1].on_clicked(
        lambda _: (
            state.__setitem__("index", (int(state["index"]) + 1) % max(len(candidates), 1)),
            redraw(),
        )
    )
    buttons[2].on_clicked(
        lambda _: (
            finish(result_from_candidate(candidates[int(state["index"])], ball_config))
            if candidates
            else None
        )
    )
    buttons[3].on_clicked(
        lambda _: (state.__setitem__("manual", True), state.__setitem__("points", []), redraw())
    )
    if allow_skip:
        skip_ax = fig.add_axes([0.64, 0.05, 0.13, 0.07])
        skip = Button(skip_ax, "跳过")
        skip.on_clicked(lambda _: finish(None))

    fig.canvas.mpl_connect("button_press_event", on_click)
    fig.canvas.mpl_connect("motion_notify_event", on_move)
    fig.canvas.mpl_connect("key_press_event", on_key)
    redraw()
    plt.show()
    return state["result"]  # type: ignore[return-value]
