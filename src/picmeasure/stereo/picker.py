"""Interactive binocular stereo picker.

The user clicks points on the rectified left image. Each click triggers an
automatic NCC search along the corresponding epipolar line in the right
image. The matched pair is triangulated to a 3D point. Right-click or ``n``
finishes the current branch and starts a new one. ``m`` toggles manual mode
where the next click on the right image sets the correspondence explicitly.
"""

from __future__ import annotations

import logging
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.widgets import Button

from picmeasure.ball.confirmation import confirm_reference_ball
from picmeasure.precision import PointPreview, magnifier_crop, snap_to_centerline, snap_to_edge
from picmeasure.stereo.annotated import render_stereo_annotated
from picmeasure.stereo.calibration import (
    build_rectification,
    calibration_from_config,
    rectify_image,
)
from picmeasure.stereo.correspondence import match_along_epipolar_line
from picmeasure.stereo.geometry import polyline_length_3d, triangulate_rectified
from picmeasure.stereo.io import save_stereo_measurements
from picmeasure.stereo.models import (
    StereoBranch,
    StereoDiameterMeasurement,
    StereoMeasurementFile,
)

if TYPE_CHECKING:
    from picmeasure.config import AppConfig

logger = logging.getLogger(__name__)


_CURRENT_COLOR = (255, 255, 0)
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


def _bgr_to_rgb_int(idx: int) -> tuple[int, int, int]:
    return _PALETTE[idx % len(_PALETTE)]


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


def stereo_measure_clicks(
    left_path: Path,
    right_path: Path,
    output_path: Path,
    app_config: AppConfig,
    annotated_path: Path | None = None,
) -> StereoMeasurementFile:
    """Run the interactive binocular stereo measurement picker.

    Args:
        left_path: Path to the left camera image.
        right_path: Path to the right camera image.
        output_path: Destination JSON file.
        app_config: Application configuration including ``stereo`` parameters.
        annotated_path: Optional path for the annotated side-by-side image.
            Defaults to ``output_path`` with ``_annotated.jpg`` suffix.

    Returns:
        A ``StereoMeasurementFile`` with all measured branches.
    """
    left_bgr = cv2.imread(str(left_path))
    right_bgr = cv2.imread(str(right_path))
    _configure_chinese_font()
    if left_bgr is None:
        raise FileNotFoundError(f"无法加载左图：{left_path}")
    if right_bgr is None:
        raise FileNotFoundError(f"无法加载右图：{right_path}")

    h, w = left_bgr.shape[:2]
    image_size = (w, h)

    stereo_cfg = app_config.stereo
    if not stereo_cfg.enabled:
        raise ValueError("双目模式未在配置中启用，请设置 stereo.enabled = true")

    calibration = calibration_from_config(stereo_cfg, image_size)
    rect_maps = build_rectification(calibration)

    rect_left = rectify_image(left_bgr, rect_maps.map1x, rect_maps.map1y)
    rect_right = rectify_image(right_bgr, rect_maps.map2x, rect_maps.map2y)

    # Ball confirmation is optional in stereo mode and uses rectified coordinates.
    left_ball = confirm_reference_ball(
        rect_left, app_config.ball, app_config.precision, allow_skip=True
    )
    right_ball = confirm_reference_ball(
        rect_right, app_config.ball, app_config.precision, allow_skip=True
    )
    triangulated_ball_diameter: float | None = None
    if (
        left_ball is not None
        and right_ball is not None
        and left_ball.detected
        and right_ball.detected
        and left_ball.ball_center_xy is not None
        and right_ball.ball_center_xy is not None
    ):
        try:
            pt3d = triangulate_rectified(
                left_ball.ball_center_xy,
                right_ball.ball_center_xy,
                rect_maps.p1,
                rect_maps.p2,
            )
            # The ball diameter in 3D is the distance from the camera plane to
            # the front-most point times 2, which is approximately 2*Z for a
            # ball facing the camera.
            triangulated_ball_diameter = 2.0 * pt3d.z
        except ValueError as exc:
            logger.warning("Could not triangulate reference ball center: %s", exc)

    unit = app_config.output_unit

    sm = StereoMeasurementFile(
        left_image_path=str(left_path),
        right_image_path=str(right_path),
        unit=unit,
        baseline_units=calibration.baseline_units,
        focal_length_px=float(rect_maps.p1[0, 0]),
        principal_point=(float(rect_maps.p1[0, 2]), float(rect_maps.p1[1, 2])),
        rotation=calibration.r.tolist(),
        translation=calibration.t.tolist(),
        distortion_coefficients=calibration.d.tolist(),
        left_ball=left_ball,
        right_ball=right_ball,
        triangulated_ball_diameter_units=triangulated_ball_diameter,
        branches=[StereoBranch(branch_id=1, unit=unit)],
    )

    fig = plt.figure(figsize=(16, 9))
    # Reserve the bottom strip for control buttons.
    ax_left = fig.add_axes([0.05, 0.18, 0.43, 0.75])
    ax_right = fig.add_axes([0.52, 0.18, 0.43, 0.75])
    ax_left.imshow(cv2.cvtColor(rect_left, cv2.COLOR_BGR2RGB))
    ax_right.imshow(cv2.cvtColor(rect_right, cv2.COLOR_BGR2RGB))
    ax_left.set_title("左图：点击添加顶点")
    ax_right.set_title("右图：自动匹配；按 m 或点“手动”切换手动模式")
    zoom_ax = fig.add_axes([0.42, 0.70, 0.16, 0.20], zorder=20)
    status = fig.text(0.02, 0.145, "", fontsize=9, va="top")

    # Control buttons.
    button_height = 0.06
    button_width = 0.09
    button_y = 0.05
    button_spacing = 0.015
    button_colors = {
        "undo": "#FFCCCC",
        "next": "#CCFFCC",
        "manual": "#E6CCFF",
        "save": "#CCCCFF",
        "quit": "#FFFFCC",
    }

    ax_undo = fig.add_axes([button_spacing, button_y, button_width, button_height])
    ax_next = fig.add_axes(
        [button_spacing + (button_width + button_spacing), button_y, button_width, button_height]
    )
    ax_manual = fig.add_axes(
        [
            button_spacing + 2 * (button_width + button_spacing),
            button_y,
            button_width,
            button_height,
        ]
    )
    ax_mode = fig.add_axes(
        [
            button_spacing + 3 * (button_width + button_spacing),
            button_y,
            button_width,
            button_height,
        ]
    )
    ax_confirm = fig.add_axes(
        [
            button_spacing + 4 * (button_width + button_spacing),
            button_y,
            button_width,
            button_height,
        ]
    )
    ax_overlay = fig.add_axes(
        [
            button_spacing + 5 * (button_width + button_spacing),
            button_y,
            button_width,
            button_height,
        ]
    )
    ax_save = fig.add_axes(
        [
            button_spacing + 6 * (button_width + button_spacing),
            button_y,
            button_width,
            button_height,
        ]
    )
    ax_quit = fig.add_axes(
        [
            button_spacing + 7 * (button_width + button_spacing),
            button_y,
            button_width,
            button_height,
        ]
    )

    btn_undo = Button(ax_undo, "撤销 (u)", color=button_colors["undo"])
    btn_next = Button(ax_next, "下一条 (n)", color=button_colors["next"])
    btn_manual = Button(ax_manual, "手动 (m)", color=button_colors["manual"])
    btn_mode = Button(ax_mode, "直径 (d)")
    btn_confirm = Button(ax_confirm, "确认")
    btn_overlay = Button(ax_overlay, "隐藏 (v)")
    btn_save = Button(ax_save, "保存 (s)", color=button_colors["save"])
    btn_quit = Button(ax_quit, "退出 (q)", color=button_colors["quit"])

    artists: list = []
    saved = {"value": False}
    manual_mode = {"value": False}
    pending_vertex = {"value": None}  # type: ignore[var-annotated]
    mode = {"value": "length"}
    overlay = {"value": True}
    snapping = {"value": True}
    preview = {"value": None}  # (PointPreview, right point, Point3D)
    diameter_first = {"value": None}  # (left point, right point, Point3D)

    def _clear() -> None:
        for a in artists:
            with suppress(Exception):
                a.remove()
        artists.clear()

    def _redraw() -> None:
        _clear()
        for b in sm.branches:
            is_current = b is sm.branches[-1]
            rgb = _CURRENT_COLOR if is_current else _bgr_to_rgb_int(b.branch_id - 1)
            rgb_norm = tuple(c / 255.0 for c in rgb)

            if overlay["value"] and len(b.vertices_left) >= 2:
                xs = [v[0] for v in b.vertices_left]
                ys = [v[1] for v in b.vertices_left]
                (line,) = ax_left.plot(xs, ys, color=rgb_norm, linewidth=1.5, alpha=0.72)
                artists.append(line)
                xs_r = [v[0] for v in b.vertices_right]
                ys_r = [v[1] for v in b.vertices_right]
                (line_r,) = ax_right.plot(xs_r, ys_r, color=rgb_norm, linewidth=1.5, alpha=0.72)
                artists.append(line_r)

            for (lx, ly), (rx, ry) in zip(b.vertices_left, b.vertices_right, strict=False):
                if not overlay["value"]:
                    continue
                sc_l = ax_left.scatter(
                    [lx], [ly], facecolors="none", edgecolors=rgb_norm, s=24, zorder=5
                )
                sc_r = ax_right.scatter(
                    [rx], [ry], facecolors="none", edgecolors=rgb_norm, s=24, zorder=5
                )
                artists.extend([sc_l, sc_r])
            for diameter in b.diameter_measurements:
                if overlay["value"]:
                    for target_ax, edges in (
                        (ax_left, diameter.edges_left),
                        (ax_right, diameter.edges_right),
                    ):
                        p1, p2 = edges
                        (line,) = target_ax.plot(
                            [p1[0], p2[0]],
                            [p1[1], p2[1]],
                            color=rgb_norm,
                            linewidth=1.2,
                            alpha=0.75,
                        )
                        marks = target_ax.scatter(
                            [p1[0], p2[0]], [p1[1], p2[1]], marker="+", color=rgb_norm, s=35
                        )
                        artists.extend([line, marks])

        current_preview = preview["value"]
        if overlay["value"] and current_preview is not None:
            left_preview, right_point, _ = current_preview
            raw = left_preview.raw
            candidate = left_preview.candidate
            raw_mark = ax_left.scatter(
                [raw[0]], [raw[1]], marker="+", color="white", s=35, zorder=9
            )
            candidate_mark = ax_left.scatter(
                [candidate[0]], [candidate[1]], facecolors="none", edgecolors="cyan", s=55, zorder=9
            )
            right_mark = ax_right.scatter(
                [right_point[0]],
                [right_point[1]],
                facecolors="none",
                edgecolors="cyan",
                s=55,
                zorder=9,
            )
            artists.extend([raw_mark, candidate_mark, right_mark])

        ax_left.set_title(_title(sm, manual_mode["value"]))
        snap_text = "已吸附" if current_preview and current_preview[0].snapped else "未吸附"
        status.set_text(
            f"模式：{'长度' if mode['value'] == 'length' else '直径'} | "
            f"吸附：{'开' if snapping['value'] else '关'} | "
            f"{snap_text if current_preview else '点击生成候选，Enter 确认'}"
        )
        fig.canvas.draw_idle()

    def _finish_current() -> None:
        current = sm.branches[-1]
        if not current.vertices_left:
            return
        next_id = current.branch_id + 1
        sm.branches.append(StereoBranch(branch_id=next_id, unit=unit))
        manual_mode["value"] = False
        pending_vertex["value"] = None

    def _add_vertex(left_pt: tuple[int, int], right_pt: tuple[int, int]) -> None:
        current = sm.branches[-1]
        current.vertices_left.append(left_pt)
        current.vertices_right.append(right_pt)
        try:
            pt3d = triangulate_rectified(left_pt, right_pt, rect_maps.p1, rect_maps.p2)
            current.vertices_3d.append(pt3d)
        except ValueError as exc:
            logger.warning("Triangulation failed for %s / %s: %s", left_pt, right_pt, exc)
        current.length_units = polyline_length_3d(current.vertices_3d)
        _redraw()

    def _undo() -> None:
        current = sm.branches[-1]
        preview["value"] = None
        if diameter_first["value"] is not None:
            diameter_first["value"] = None
        elif mode["value"] == "diameter" and current.diameter_measurements:
            current.diameter_measurements.pop()
        elif current.vertices_left:
            current.vertices_left.pop()
            current.vertices_right.pop()
            if current.vertices_3d:
                current.vertices_3d.pop()
        elif len(sm.branches) > 1:
            sm.branches.pop()
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

    def _set_preview(left_preview: PointPreview, right_point: tuple[int, int]) -> None:
        try:
            point_3d = triangulate_rectified(
                left_preview.candidate, right_point, rect_maps.p1, rect_maps.p2
            )
        except ValueError as exc:
            ax_right.set_title(f"三角化失败：{exc}")
            fig.canvas.draw_idle()
            return
        preview["value"] = (left_preview, right_point, point_3d)
        _redraw()

    def _confirm_preview() -> None:
        selected = preview["value"]
        if selected is None:
            return
        left_preview, right_point, point_3d = selected
        if mode["value"] == "length":
            _add_vertex(left_preview.candidate, right_point)
        elif diameter_first["value"] is None:
            diameter_first["value"] = (left_preview.candidate, right_point, point_3d)
        else:
            first_left, first_right, first_3d = diameter_first["value"]
            diameter = float(np.linalg.norm(point_3d.array() - first_3d.array()))
            current = sm.branches[-1]
            current.diameter_measurements.append(
                StereoDiameterMeasurement(
                    len(current.diameter_measurements) + 1,
                    (first_left, left_preview.candidate),
                    (first_right, right_point),
                    (first_3d, point_3d),
                    diameter,
                    unit,
                )
            )
            diameter_first["value"] = None
        preview["value"] = None
        _redraw()

    def _toggle_manual() -> None:
        manual_mode["value"] = not manual_mode["value"]
        pending_vertex["value"] = None
        if manual_mode["value"]:
            ax_right.set_title("右图：请点击匹配点")
        else:
            ax_right.set_title("右图：自动匹配；按 m 或点“手动”切换手动模式")
        fig.canvas.draw_idle()
        _redraw()

    def _save() -> None:
        saved["value"] = True
        plt.close(fig)

    def _quit() -> None:
        plt.close(fig)

    def on_click(event):  # type: ignore[no-untyped-def]
        if event.xdata is None or event.ydata is None:
            return
        x, y = int(round(event.xdata)), int(round(event.ydata))

        if event.inaxes == ax_left:
            raw = (x, y)
            if not snapping["value"]:
                left_preview = PointPreview(raw, raw, False)
            elif mode["value"] == "diameter":
                left_preview = snap_to_edge(rect_left, raw, app_config.precision)
            else:
                vertices = sm.branches[-1].vertices_left
                left_preview = snap_to_centerline(
                    rect_left, raw, vertices[-1] if vertices else None, app_config.precision
                )
            if manual_mode["value"]:
                pending_vertex["value"] = left_preview
                ax_right.set_title("右图：请点击匹配点")
                fig.canvas.draw_idle()
                return

            try:
                match = match_along_epipolar_line(
                    rect_left, rect_right, left_preview.candidate, stereo_cfg.correspondence
                )
                _set_preview(
                    left_preview, (int(round(match.right_pt[0])), int(round(match.right_pt[1])))
                )
            except RuntimeError as exc:
                logger.warning("Automatic correspondence failed: %s", exc)
                ax_right.set_title(f"自动匹配失败：{exc}；按 m 或点“手动”切换手动模式")
                fig.canvas.draw_idle()

        elif event.inaxes == ax_right:
            if manual_mode["value"] and pending_vertex["value"] is not None:
                _set_preview(pending_vertex["value"], (x, y))
                manual_mode["value"] = False
                pending_vertex["value"] = None
                ax_right.set_title("右图：自动匹配；按 m 或点“手动”切换手动模式")

    def on_key(event):  # type: ignore[no-untyped-def]
        key = (event.key or "").lower()
        if key in ("enter", "return"):
            _confirm_preview()
        elif key == "escape":
            preview["value"] = None
            pending_vertex["value"] = None
            _redraw()
        elif key == "a":
            snapping["value"] = not snapping["value"]
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
            left_preview, right_point, _ = preview["value"]
            left_preview.nudge(dx, dy, rect_left.shape)
            shifted_right = (right_point[0] + dx, right_point[1] + dy)
            _set_preview(left_preview, shifted_right)
        elif key == "d":
            _toggle_mode()
        elif key == "v":
            _toggle_overlay()
        elif key == "n":
            _finish_current()
            _redraw()
        elif key == "u":
            _undo()
        elif key == "m":
            _toggle_manual()
        elif key == "s":
            _save()
        elif key == "q":
            _quit()

    def on_move(event):  # type: ignore[no-untyped-def]
        if event.inaxes not in (ax_left, ax_right) or event.xdata is None or event.ydata is None:
            return
        image = rect_left if event.inaxes == ax_left else rect_right
        crop, _ = magnifier_crop(
            image,
            (int(round(event.xdata)), int(round(event.ydata))),
            app_config.precision.magnifier_radius_px,
        )
        zoom_ax.clear()
        zoom_ax.imshow(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB), interpolation="nearest")
        zoom_ax.axhline((crop.shape[0] - 1) / 2, color="cyan", linewidth=0.7)
        zoom_ax.axvline((crop.shape[1] - 1) / 2, color="cyan", linewidth=0.7)
        zoom_ax.set_xticks([])
        zoom_ax.set_yticks([])
        fig.canvas.draw_idle()

    btn_undo.on_clicked(lambda _event: _undo())
    btn_next.on_clicked(lambda _event: (_finish_current(), _redraw()))
    btn_manual.on_clicked(lambda _event: _toggle_manual())
    btn_mode.on_clicked(lambda _event: _toggle_mode())
    btn_confirm.on_clicked(lambda _event: _confirm_preview())
    btn_overlay.on_clicked(lambda _event: _toggle_overlay())
    btn_save.on_clicked(lambda _event: _save())
    btn_quit.on_clicked(lambda _event: _quit())

    print(  # noqa: T201 — intentional user-facing console help
        "双目测量操作说明：\n"
        "  左键点击左图 -> 生成吸附候选并自动匹配右图\n"
        "  Enter/确认    -> 确认候选并写入结果\n"
        "  方向键         -> 微调 1px；Shift+方向键微调 5px\n"
        "  d / 模式按钮  -> 切换长度与直径模式\n"
        "  a / v          -> 切换吸附 / 显示覆盖层\n"
        "  m / 手动按钮   -> 切换手动模式（先点左图，再点右图对应点）\n"
        "  右键点击左图   -> 完成当前分支，开始下一条\n"
        "  n / 下一条按钮 -> 与右键相同\n"
        "  u / 撤销按钮   -> 撤销上一个顶点\n"
        "  s / 保存按钮   -> 保存并关闭\n"
        "  q / 退出按钮   -> 不保存直接退出\n"
        f"  基线：{calibration.baseline_units:.2f} {calibration.unit}，"
        f"焦距：{rect_maps.p1[0, 0]:.1f} px"
    )

    fig.canvas.mpl_connect("button_press_event", on_click)
    fig.canvas.mpl_connect("motion_notify_event", on_move)
    fig.canvas.mpl_connect("key_press_event", on_key)
    _redraw()
    plt.show()

    # Drop trailing empty branches.
    sm.branches = [b for b in sm.branches if b.vertices_left or b.diameter_measurements]
    for b in sm.branches:
        b.length_units = polyline_length_3d(b.vertices_3d)

    if saved["value"]:
        save_stereo_measurements(sm, output_path)
        logger.info("Saved %d stereo measurement(s) to %s", len(sm.branches), output_path)
        if annotated_path is None:
            annotated_path = output_path.with_name(output_path.stem + "_annotated.jpg")
        render_stereo_annotated(rect_left, rect_right, sm, annotated_path)
        logger.info("Wrote annotated stereo image to %s", annotated_path)

    return sm


def _title(sm: StereoMeasurementFile, manual: bool) -> str:
    current = sm.branches[-1] if sm.branches else None
    branch_id = current.branch_id if current else 0
    finished = sum(1 for b in sm.branches if b.vertices_left)
    total = sum(len(b.vertices_left) for b in sm.branches)
    bits = [
        f"分支 #{branch_id}",
        f"{finished} 条分支",
        f"{total} 个顶点",
        f"基线={sm.baseline_units:.2f} {sm.unit}",
    ]
    if current and current.vertices_3d:
        bits.append(f"当前={current.length_units:.1f} {sm.unit}")
    bits.append(
        "Enter=确认 d=长度/直径 a=吸附 v=覆盖层 m=手动 u=撤销 s=保存"
        + (" 【手动模式】" if manual else "")
    )
    return "  |  ".join(bits)
