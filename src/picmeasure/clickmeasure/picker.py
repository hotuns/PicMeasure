"""Interactive ruler tool: ball calibrates scale, polyline clicks measure length.

Workflow:
    1. Detect the orange-red reference ball once → derive pixels-per-unit.
    2. User clicks vertices along a branch (polyline). Total polyline length
       updates live and is shown in the configured output unit.
    3. Right-click or 'n' finishes the current branch and starts the next.
    4. 's' saves a JSON of all branches + writes an annotated image.

Output JSON schema::

    {
      "image_path": "datas/1.jpg",
      "scale": {
        "pixels_per_unit": 6.27,
        "unit": "cm",
        "ball_center_xy": [1933, 1121],
        "ball_radius_px": 47.0
      },
      "branches": [
        {
          "branch_id": 1,
          "vertices": [[x, y], ...],
          "length_pixels": 612.5,
          "length_units": 97.7,
          "unit": "cm"
        }
      ]
    }
"""

from __future__ import annotations

import json
import logging
import math
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy.typing as npt

    from picmeasure.config import AppConfig

logger = logging.getLogger(__name__)

# Distinct colours for finalised branches; the current (in-progress)
# branch is always rendered in bright yellow.
_PALETTE: tuple[tuple[int, int, int], ...] = (
    (50, 205, 50),  # lime green
    (30, 144, 255),  # dodger blue
    (255, 165, 0),  # orange
    (238, 130, 238),  # violet
    (220, 20, 60),  # crimson
    (0, 206, 209),  # dark turquoise
    (255, 105, 180),  # hot pink
    (154, 205, 50),  # yellow-green
)
_CURRENT_COLOR: tuple[int, int, int] = (255, 255, 0)  # bright yellow


@dataclass
class DiameterMeasurement:
    """One manually confirmed branch cross-section."""

    section_id: int
    edge_points: tuple[tuple[int, int], tuple[int, int]]
    diameter_pixels: float
    diameter_units: float
    unit: str = "cm"


@dataclass
class BranchPolyline:
    """One measured branch as a polyline of clicked vertices."""

    branch_id: int
    vertices: list[tuple[int, int]] = field(default_factory=list)
    length_pixels: float = 0.0
    length_units: float = 0.0
    unit: str = "cm"
    diameter_measurements: list[DiameterMeasurement] = field(default_factory=list)


@dataclass
class MeasurementFile:
    """Top-level measurement container: scale + all measured branches."""

    image_path: str
    pixels_per_unit: float | None
    unit: str
    ball_center_xy: tuple[int, int] | None
    ball_radius_px: float | None
    ball_source: str = "auto"
    ball_candidate_score: float | None = None
    branches: list[BranchPolyline] = field(default_factory=list)


def polyline_length_pixels(vertices: list[tuple[int, int]]) -> float:
    """Sum the Euclidean lengths of the polyline's segments."""
    if len(vertices) < 2:
        return 0.0
    total = 0.0
    for i in range(len(vertices) - 1):
        x1, y1 = vertices[i]
        x2, y2 = vertices[i + 1]
        total += math.hypot(x2 - x1, y2 - y1)
    return total


def save_measurements(mf: MeasurementFile, output_path: Path) -> None:
    """Persist a measurement file as JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 2,
        "mode": "monocular",
        "images": {"primary": mf.image_path},
        "calibration": {
            "pixels_per_unit": mf.pixels_per_unit,
            "unit": mf.unit,
            "ball_center_xy": list(mf.ball_center_xy) if mf.ball_center_xy else None,
            "ball_radius_px": mf.ball_radius_px,
            "physical_diameter": None
            if mf.pixels_per_unit is None or mf.ball_radius_px is None
            else 2.0 * mf.ball_radius_px / mf.pixels_per_unit,
            "source": mf.ball_source,
            "candidate_score": mf.ball_candidate_score,
        },
        "branches": [
            {
                "branch_id": b.branch_id,
                "vertices": [list(v) for v in b.vertices],
                "length_pixels": round(b.length_pixels, 2),
                "length_units": round(b.length_units, 2),
                "unit": b.unit,
                "diameter_measurements": [
                    {
                        "section_id": d.section_id,
                        "edge_points": [list(d.edge_points[0]), list(d.edge_points[1])],
                        "diameter_pixels": round(d.diameter_pixels, 2),
                        "diameter_units": round(d.diameter_units, 2),
                        "unit": d.unit,
                    }
                    for d in b.diameter_measurements
                ],
            }
            for b in mf.branches
            if b.vertices or b.diameter_measurements
        ],
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_measurements(path: Path) -> MeasurementFile:
    """Load a measurement file from JSON."""
    data = json.loads(path.read_text(encoding="utf-8"))
    is_v2 = data.get("schema_version") == 2
    scale = data.get("calibration", {}) if is_v2 else data.get("scale", {})
    center = scale.get("ball_center_xy")
    mf = MeasurementFile(
        image_path=str(data.get("images", {}).get("primary", ""))
        if is_v2
        else str(data.get("image_path", "")),
        pixels_per_unit=scale.get("pixels_per_unit"),
        unit=str(scale.get("unit", "cm")),
        ball_center_xy=tuple(center) if center else None,  # type: ignore[arg-type]
        ball_radius_px=scale.get("ball_radius_px"),
        ball_source=str(scale.get("source", "auto")),
        ball_candidate_score=scale.get("candidate_score"),
    )
    for raw in data.get("branches", []):
        verts = [(int(v[0]), int(v[1])) for v in raw.get("vertices", [])]
        diameters = []
        for diameter in raw.get("diameter_measurements", []):
            edges = diameter.get("edge_points", [[0, 0], [0, 0]])
            diameters.append(
                DiameterMeasurement(
                    section_id=int(diameter["section_id"]),
                    edge_points=(tuple(edges[0]), tuple(edges[1])),  # type: ignore[arg-type]
                    diameter_pixels=float(diameter.get("diameter_pixels", 0.0)),
                    diameter_units=float(diameter.get("diameter_units", 0.0)),
                    unit=str(diameter.get("unit", mf.unit)),
                )
            )
        mf.branches.append(
            BranchPolyline(
                branch_id=int(raw["branch_id"]),
                vertices=verts,
                length_pixels=float(raw.get("length_pixels", 0.0)),
                length_units=float(raw.get("length_units", 0.0)),
                unit=str(raw.get("unit", mf.unit)),
                diameter_measurements=diameters,
            )
        )
    return mf


def _configure_chinese_font() -> None:
    """Prefer Windows CJK fonts so Chinese UI text renders correctly."""
    import matplotlib

    matplotlib.rcParams["font.sans-serif"] = [
        "Microsoft YaHei",
        "SimHei",
        "SimSun",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    matplotlib.rcParams["axes.unicode_minus"] = False


def measure_clicks(
    image_path: Path,
    output_path: Path,
    app_config: AppConfig,
    annotated_path: Path | None = None,
) -> MeasurementFile:
    """Open an interactive picker; click polylines to measure branches.

    Controls (printed on launch):
        * Left click  -> add vertex to current branch
        * Right click -> finish current branch, start a new one
        * 'n'         -> same as right click
        * 'u'         -> undo last vertex
        * 's'         -> save and close
        * 'q'         -> quit without saving

    Args:
        image_path: Image to measure on.
        output_path: Destination JSON file.
        app_config: App config; used for ball detection and output unit.
        annotated_path: Optional path for the annotated image. Defaults to
            ``output_path`` with ``_annotated.jpg`` suffix.
    """
    import cv2
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle
    from matplotlib.widgets import Button

    from picmeasure.ball.confirmation import confirm_reference_ball
    from picmeasure.precision import PointPreview, magnifier_crop, snap_to_centerline, snap_to_edge

    _configure_chinese_font()

    img_bgr = cv2.imread(str(image_path))
    if img_bgr is None:
        raise FileNotFoundError(f"无法加载图像：{image_path}")
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

    ball = confirm_reference_ball(img_bgr, app_config.ball, app_config.precision)
    if ball is None or not ball.detected or ball.pixels_per_unit is None:
        detail = ball.error_message if ball is not None else "用户未确认参考球"
        raise RuntimeError(
            f"未在 {image_path} 中检测到参考球：{detail or '未知原因'}。无法建立比例尺。"
        )
    unit = app_config.output_unit
    pixels_per_unit = ball.pixels_per_unit / 10.0 if unit == "mm" else ball.pixels_per_unit

    mf = MeasurementFile(
        image_path=str(image_path),
        pixels_per_unit=pixels_per_unit,
        unit=unit,
        ball_center_xy=ball.ball_center_xy,
        ball_radius_px=ball.ball_radius_px,
        ball_source=ball.source,
        ball_candidate_score=ball.candidate_score,
        branches=[BranchPolyline(branch_id=1, unit=unit)],
    )

    fig = plt.figure(figsize=(12, 9))
    # Leave room at the bottom for control buttons.
    ax = fig.add_axes([0.05, 0.20, 0.72, 0.75])
    ax.imshow(img_rgb)
    zoom_ax = fig.add_axes([0.79, 0.56, 0.19, 0.35])
    result_ax = fig.add_axes([0.79, 0.20, 0.19, 0.30])
    result_ax.axis("off")
    status = fig.text(0.05, 0.145, "", fontsize=9, va="top")

    if ball.ball_center_xy and ball.ball_radius_px:
        ax.add_patch(
            Circle(
                ball.ball_center_xy,
                ball.ball_radius_px,
                fill=False,
                edgecolor="cyan",
                linewidth=2.5,
                zorder=4,
            )
        )
        ax.text(
            ball.ball_center_xy[0],
            ball.ball_center_xy[1] - ball.ball_radius_px - 10,
            f"参考球 Ø ({pixels_per_unit:.2f} px/{unit})",
            color="cyan",
            fontsize=10,
            ha="center",
            va="bottom",
            bbox={"facecolor": "black", "alpha": 0.6, "pad": 2, "edgecolor": "none"},
            zorder=6,
        )

    # Control buttons.
    button_height = 0.06
    button_width = 0.10
    button_y = 0.05
    button_spacing = 0.02
    button_colors = {
        "undo": "#FFCCCC",
        "next": "#CCFFCC",
        "save": "#CCCCFF",
        "quit": "#FFFFCC",
    }

    ax_undo = fig.add_axes([button_spacing, button_y, button_width, button_height])
    ax_next = fig.add_axes(
        [button_spacing + (button_width + button_spacing), button_y, button_width, button_height]
    )
    ax_mode = fig.add_axes(
        [
            button_spacing + 2 * (button_width + button_spacing),
            button_y,
            button_width,
            button_height,
        ]
    )
    ax_confirm = fig.add_axes(
        [
            button_spacing + 3 * (button_width + button_spacing),
            button_y,
            button_width,
            button_height,
        ]
    )
    ax_overlay = fig.add_axes(
        [
            button_spacing + 4 * (button_width + button_spacing),
            button_y,
            button_width,
            button_height,
        ]
    )
    ax_save = fig.add_axes(
        [
            button_spacing + 5 * (button_width + button_spacing),
            button_y,
            button_width,
            button_height,
        ]
    )
    ax_quit = fig.add_axes(
        [
            button_spacing + 6 * (button_width + button_spacing),
            button_y,
            button_width,
            button_height,
        ]
    )

    btn_undo = Button(ax_undo, "撤销 (u)", color=button_colors["undo"])
    btn_next = Button(ax_next, "下一条 (n)", color=button_colors["next"])
    btn_mode = Button(ax_mode, "直径 (d)")
    btn_confirm = Button(ax_confirm, "确认 (Enter)")
    btn_overlay = Button(ax_overlay, "隐藏 (v)")
    btn_save = Button(ax_save, "保存 (s)", color=button_colors["save"])
    btn_quit = Button(ax_quit, "退出 (q)", color=button_colors["quit"])

    # Artists rebuilt on every redraw.
    artists: list = []
    saved = {"value": False}
    mode = {"value": "length"}
    overlay = {"value": True}
    snapping = {"value": True}
    preview: dict[str, PointPreview | None] = {"value": None}
    diameter_first: dict[str, tuple[int, int] | None] = {"value": None}

    def _clear() -> None:
        for a in artists:
            with suppress(Exception):
                a.remove()
        artists.clear()

    def _redraw() -> None:
        _clear()
        rows: list[str] = []
        for b in mf.branches:
            is_current = b is mf.branches[-1]
            rgb_int = _CURRENT_COLOR if is_current else _PALETTE[(b.branch_id - 1) % len(_PALETTE)]
            rgb = tuple(c / 255.0 for c in rgb_int)
            b.length_pixels = polyline_length_pixels(b.vertices)
            b.length_units = b.length_pixels / pixels_per_unit
            if overlay["value"] and len(b.vertices) >= 2:
                xs = [v[0] for v in b.vertices]
                ys = [v[1] for v in b.vertices]
                (line,) = ax.plot(xs, ys, color=rgb, linewidth=1.5, alpha=0.72, zorder=5)
                artists.append(line)
            if overlay["value"] and b.vertices:
                xs = [v[0] for v in b.vertices]
                ys = [v[1] for v in b.vertices]
                sc = ax.scatter(
                    xs, ys, facecolors="none", edgecolors=rgb, s=24, linewidths=1.0, zorder=6
                )
                artists.append(sc)
            for diameter in b.diameter_measurements:
                rows.append(
                    f"#{b.branch_id} D{diameter.section_id}: {diameter.diameter_units:.2f} {unit}"
                )
                if overlay["value"]:
                    p1, p2 = diameter.edge_points
                    (line,) = ax.plot(
                        [p1[0], p2[0]],
                        [p1[1], p2[1]],
                        color=rgb,
                        linewidth=1.2,
                        alpha=0.75,
                        zorder=5,
                    )
                    marks = ax.scatter(
                        [p1[0], p2[0]],
                        [p1[1], p2[1]],
                        marker="+",
                        color=rgb,
                        s=35,
                        linewidths=1.0,
                        zorder=6,
                    )
                    artists.extend([line, marks])
            if b.vertices:
                rows.insert(0, f"#{b.branch_id} L: {b.length_units:.2f} {unit}")
        if overlay["value"] and diameter_first["value"] is not None:
            point = diameter_first["value"]
            mark = ax.scatter([point[0]], [point[1]], marker="+", color="cyan", s=45, zorder=8)
            artists.append(mark)
        current_preview = preview["value"]
        if overlay["value"] and current_preview is not None:
            raw, candidate = current_preview.raw, current_preview.candidate
            (guide,) = ax.plot(
                [raw[0], candidate[0]],
                [raw[1], candidate[1]],
                "--",
                color="white",
                linewidth=0.8,
                zorder=8,
            )
            raw_mark = ax.scatter([raw[0]], [raw[1]], marker="+", color="white", s=35, zorder=9)
            candidate_mark = ax.scatter(
                [candidate[0]],
                [candidate[1]],
                facecolors="none",
                edgecolors="cyan",
                s=55,
                linewidths=1.2,
                zorder=9,
            )
            artists.extend([guide, raw_mark, candidate_mark])
        result_ax.clear()
        result_ax.axis("off")
        result_ax.text(0, 1, "\n".join(rows[:14]) or "暂无测量", va="top", fontsize=9)
        state_text = "已吸附" if current_preview and current_preview.snapped else "未吸附"
        status.set_text(
            f"模式：{'长度' if mode['value'] == 'length' else '直径'}  |  "
            f"吸附：{'开' if snapping['value'] else '关'}  |  "
            f"{state_text if current_preview else '点击生成候选'}"
        )
        ax.set_title(_title(mf, pixels_per_unit, unit))
        fig.canvas.draw_idle()

    def _finish_current() -> None:
        current = mf.branches[-1]
        if not current.vertices:
            return
        next_id = current.branch_id + 1
        mf.branches.append(BranchPolyline(branch_id=next_id, unit=unit))

    def _undo() -> None:
        current = mf.branches[-1]
        preview["value"] = None
        if diameter_first["value"] is not None:
            diameter_first["value"] = None
        elif mode["value"] == "diameter" and current.diameter_measurements:
            current.diameter_measurements.pop()
        elif current.vertices:
            current.vertices.pop()
        elif len(mf.branches) > 1:
            mf.branches.pop()
        _redraw()

    def _toggle_mode() -> None:
        mode["value"] = "diameter" if mode["value"] == "length" else "length"
        preview["value"] = None
        diameter_first["value"] = None
        btn_mode.label.set_text("长度 (d)" if mode["value"] == "diameter" else "直径 (d)")
        _redraw()

    def _toggle_overlay() -> None:
        overlay["value"] = not overlay["value"]
        btn_overlay.label.set_text("显示 (v)" if not overlay["value"] else "隐藏 (v)")
        _redraw()

    def _confirm_preview() -> None:
        selected = preview["value"]
        if selected is None:
            return
        point = selected.candidate
        current = mf.branches[-1]
        if mode["value"] == "length":
            current.vertices.append(point)
        elif diameter_first["value"] is None:
            diameter_first["value"] = point
        else:
            first = diameter_first["value"]
            pixels = math.hypot(point[0] - first[0], point[1] - first[1])
            current.diameter_measurements.append(
                DiameterMeasurement(
                    len(current.diameter_measurements) + 1,
                    (first, point),
                    pixels,
                    pixels / pixels_per_unit,
                    unit,
                )
            )
            diameter_first["value"] = None
        preview["value"] = None
        _redraw()

    def _save() -> None:
        saved["value"] = True
        plt.close(fig)

    def _quit() -> None:
        plt.close(fig)

    def on_click(event):  # type: ignore[no-untyped-def]
        if event.inaxes != ax or event.xdata is None or event.ydata is None:
            return
        x, y = int(round(event.xdata)), int(round(event.ydata))
        if event.button == 1:
            point = (x, y)
            if not snapping["value"]:
                preview["value"] = PointPreview(point, point, False)
            elif mode["value"] == "diameter":
                preview["value"] = snap_to_edge(img_bgr, point, app_config.precision)
            else:
                vertices = mf.branches[-1].vertices
                preview["value"] = snap_to_centerline(
                    img_bgr, point, vertices[-1] if vertices else None, app_config.precision
                )
            _redraw()
        elif event.button == 3:
            _finish_current()
            _redraw()

    def on_key(event):  # type: ignore[no-untyped-def]
        key = (event.key or "").lower()
        if key in ("enter", "return"):
            _confirm_preview()
        elif key == "escape":
            preview["value"] = None
            _redraw()
        elif (
            key
            in (
                "left",
                "right",
                "up",
                "down",
                "shift+left",
                "shift+right",
                "shift+up",
                "shift+down",
            )
            and preview["value"]
        ):
            step = 5 if key.startswith("shift+") else 1
            direction = key.removeprefix("shift+")
            dx = -step if direction == "left" else step if direction == "right" else 0
            dy = -step if direction == "up" else step if direction == "down" else 0
            preview["value"].nudge(dx, dy, img_bgr.shape)
            _redraw()
        elif key == "a":
            snapping["value"] = not snapping["value"]
            _redraw()
        elif key == "d":
            _toggle_mode()
        elif key == "v":
            _toggle_overlay()
        elif key == "n":
            _finish_current()
            _redraw()
        elif key == "u":
            _undo()
        elif key == "s":
            _save()
        elif key == "q":
            _quit()

    def on_move(event):  # type: ignore[no-untyped-def]
        if event.inaxes != ax or event.xdata is None or event.ydata is None:
            return
        crop, _ = magnifier_crop(
            img_rgb,
            (int(round(event.xdata)), int(round(event.ydata))),
            app_config.precision.magnifier_radius_px,
        )
        zoom_ax.clear()
        zoom_ax.imshow(crop, interpolation="nearest")
        zoom_ax.axhline((crop.shape[0] - 1) / 2, color="cyan", linewidth=0.7)
        zoom_ax.axvline((crop.shape[1] - 1) / 2, color="cyan", linewidth=0.7)
        zoom_ax.set_xticks([])
        zoom_ax.set_yticks([])
        fig.canvas.draw_idle()

    btn_undo.on_clicked(lambda _event: _undo())
    btn_next.on_clicked(lambda _event: (_finish_current(), _redraw()))
    btn_mode.on_clicked(lambda _event: _toggle_mode())
    btn_confirm.on_clicked(lambda _event: _confirm_preview())
    btn_overlay.on_clicked(lambda _event: _toggle_overlay())
    btn_save.on_clicked(lambda _event: _save())
    btn_quit.on_clicked(lambda _event: _quit())

    print(  # noqa: T201 — intentional user-facing console help
        "单目测量操作说明：\n"
        "  左键点击   -> 生成吸附候选（不会立即落点）\n"
        "  Enter/确认 -> 确认候选并写入结果\n"
        "  方向键      -> 微调 1px；Shift+方向键微调 5px\n"
        "  d / 模式按钮 -> 切换长度与直径模式\n"
        "  a / v       -> 切换吸附 / 显示覆盖层\n"
        "  右键点击   -> 完成当前分支，开始下一条\n"
        "  n / 下一条 -> 与右键相同\n"
        "  u / 撤销   -> 撤销上一个顶点\n"
        "  s / 保存   -> 保存并关闭\n"
        "  q / 退出   -> 不保存直接退出\n"
        f"  比例尺：{pixels_per_unit:.2f} px/{unit} "
        f"（球直径={app_config.ball.known_diameter_cm:g}cm，半径={ball.ball_radius_px:.1f}px）"
    )

    fig.canvas.mpl_connect("button_press_event", on_click)
    fig.canvas.mpl_connect("motion_notify_event", on_move)
    fig.canvas.mpl_connect("key_press_event", on_key)
    _redraw()
    plt.show()

    # Drop trailing empty branches; recompute final lengths.
    mf.branches = [b for b in mf.branches if b.vertices or b.diameter_measurements]
    for b in mf.branches:
        b.length_pixels = polyline_length_pixels(b.vertices)
        b.length_units = b.length_pixels / pixels_per_unit

    if saved["value"]:
        save_measurements(mf, output_path)
        logger.info("Saved %d measurement(s) to %s", len(mf.branches), output_path)
        if annotated_path is None:
            annotated_path = output_path.with_name(output_path.stem + "_annotated.jpg")
        write_annotated_image(img_bgr, mf, annotated_path)
        logger.info("Wrote annotated image to %s", annotated_path)

    return mf


def write_annotated_image(
    img_bgr: npt.NDArray,  # type: ignore[type-arg]
    mf: MeasurementFile,
    output_path: Path,
) -> None:
    """Render ball + all polylines + length labels onto a copy of *img_bgr*."""
    import cv2

    height, width = img_bgr.shape[:2]
    annotated = __import__("numpy").full((height, width + 300, 3), 245, dtype=img_bgr.dtype)
    annotated[:, :width] = img_bgr
    summary: list[str] = []

    if mf.ball_center_xy and mf.ball_radius_px:
        cv2.circle(
            annotated,
            mf.ball_center_xy,
            int(round(mf.ball_radius_px)),
            (255, 255, 0),  # BGR cyan
            2,
        )
        label = (
            f"ref ball ({mf.pixels_per_unit:.2f} px/{mf.unit})"
            if mf.pixels_per_unit is not None
            else "ref ball"
        )
        cv2.putText(
            annotated,
            label,
            (mf.ball_center_xy[0] - 120, mf.ball_center_xy[1] - int(mf.ball_radius_px) - 15),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 0),
            1,
            cv2.LINE_AA,
        )

    for b in mf.branches:
        rgb = _PALETTE[(b.branch_id - 1) % len(_PALETTE)]
        bgr = (int(rgb[2]), int(rgb[1]), int(rgb[0]))
        for j in range(len(b.vertices) - 1):
            cv2.line(annotated, b.vertices[j], b.vertices[j + 1], bgr, 2, cv2.LINE_AA)
        for v in b.vertices:
            cv2.circle(annotated, v, 4, bgr, 1, cv2.LINE_AA)
        if b.vertices:
            summary.append(f"#{b.branch_id} length: {b.length_units:.2f} {b.unit}")
        for diameter in b.diameter_measurements:
            p1, p2 = diameter.edge_points
            cv2.line(annotated, p1, p2, bgr, 1, cv2.LINE_AA)
            cv2.drawMarker(annotated, p1, bgr, cv2.MARKER_CROSS, 7, 1, cv2.LINE_AA)
            cv2.drawMarker(annotated, p2, bgr, cv2.MARKER_CROSS, 7, 1, cv2.LINE_AA)
            summary.append(
                f"#{b.branch_id} D{diameter.section_id}: "
                f"{diameter.diameter_units:.2f} {diameter.unit}"
            )

    cv2.putText(
        annotated,
        "Measurements",
        (width + 18, 35),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (30, 30, 30),
        2,
        cv2.LINE_AA,
    )
    for index, text in enumerate(summary):
        if 70 + index * 28 >= height:
            break
        cv2.putText(
            annotated,
            text,
            (width + 18, 70 + index * 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (50, 50, 50),
            1,
            cv2.LINE_AA,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), annotated)


def _title(mf: MeasurementFile, pixels_per_unit: float, unit: str) -> str:
    current = mf.branches[-1] if mf.branches else None
    branch_id = current.branch_id if current else 0
    total_vertices = sum(len(b.vertices) for b in mf.branches)
    finished = sum(1 for b in mf.branches if b.vertices)
    bits = [
        f"分支 #{branch_id}",
        f"{finished} 条分支",
        f"{total_vertices} 个顶点",
        f"比例尺={pixels_per_unit:.2f} px/{unit}",
    ]
    if current and current.vertices:
        bits.append(f"当前={current.length_units:.1f} {unit}")
    bits.append("左键=预览 Enter=确认 d=长度/直径 a=吸附 v=覆盖层 u=撤销 s=保存")
    return "  |  ".join(bits)
