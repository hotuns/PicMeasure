"""Graphical file-selection launcher for PicMeasure.

Provides a small tkinter window with buttons for monocular and binocular
measurement. All file paths are chosen through native file dialogs, so users
do not need to type command-line arguments.
"""

from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING

from picmeasure.clickmeasure.picker import measure_clicks as _measure_clicks
from picmeasure.config import AppConfig, setup_logging
from picmeasure.stereo.picker import stereo_measure_clicks

if TYPE_CHECKING:
    from picmeasure.config import StereoConfig

logger = logging.getLogger(__name__)


_IMAGE_TYPES = [
    ("Image files", "*.jpg *.jpeg *.png *.tif *.tiff"),
    ("JPEG", "*.jpg *.jpeg"),
    ("PNG", "*.png"),
    ("TIFF", "*.tif *.tiff"),
    ("All files", "*.*"),
]


def _load_stereo_config(stereo_config_path: Path) -> StereoConfig:
    """Load StereoConfig from a dedicated TOML file."""
    from picmeasure.config import AppConfig

    data = AppConfig.from_toml(stereo_config_path)
    return data.stereo


def _select_image(title: str) -> Path | None:
    path = filedialog.askopenfilename(
        title=title,
        filetypes=_IMAGE_TYPES,
    )
    return Path(path) if path else None


def _select_stereo_config() -> Path | None:
    path = filedialog.askopenfilename(
        title="选择双目标定 TOML 文件",
        filetypes=[("TOML files", "*.toml"), ("All files", "*.*")],
    )
    return Path(path) if path else None


def _select_output_json(title: str = "保存测量结果 JSON") -> Path | None:
    path = filedialog.asksaveasfilename(
        title=title,
        defaultextension=".json",
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
    )
    return Path(path) if path else None


def _run_monocular(app_config: AppConfig) -> None:
    image_path = _select_image("选择要测量的图像")
    if image_path is None:
        return
    output_path = _select_output_json("保存测量结果 JSON")
    if output_path is None:
        return
    try:
        _measure_clicks(image_path, output_path, app_config=app_config)
        messagebox.showinfo("完成", f"测量结果已保存至：\n{output_path}")
    except Exception as exc:  # noqa: BLE001 — user-facing fallback
        logger.exception("Monocular measurement failed")
        messagebox.showerror("错误", f"测量失败：\n{exc}")


def _run_stereo(app_config: AppConfig) -> None:
    left_path = _select_image("选择左相机图像")
    if left_path is None:
        return
    right_path = _select_image("选择右相机图像")
    if right_path is None:
        return
    stereo_config_path = _select_stereo_config()
    if stereo_config_path is None:
        return
    output_path = _select_output_json("保存双目测量结果 JSON")
    if output_path is None:
        return

    try:
        stereo_cfg = _load_stereo_config(stereo_config_path)
        if not stereo_cfg.enabled:
            stereo_cfg.enabled = True
        app_config.stereo = stereo_cfg
        stereo_measure_clicks(left_path, right_path, output_path, app_config=app_config)
        messagebox.showinfo("完成", f"双目测量结果已保存至：\n{output_path}")
    except Exception as exc:  # noqa: BLE001 — user-facing fallback
        logger.exception("Stereo measurement failed")
        messagebox.showerror("错误", f"双目测量失败：\n{exc}")


def launch_gui(app_config: AppConfig | None = None) -> None:
    """Open the PicMeasure launcher window."""
    if app_config is None:
        app_config = AppConfig()
    setup_logging(app_config.logging)

    root = tk.Tk()
    root.title("PicMeasure 图像测长")
    root.geometry("360x200")
    root.resizable(False, False)

    label = tk.Label(
        root,
        text="选择测量模式",
        font=("Arial", 14, "bold"),
    )
    label.pack(pady=20)

    mono_btn = tk.Button(
        root,
        text="单目图像（参考球 + 点击测长）",
        width=30,
        command=lambda: _run_monocular(app_config),
    )
    mono_btn.pack(pady=5)

    stereo_btn = tk.Button(
        root,
        text="双目立体视觉",
        width=30,
        command=lambda: _run_stereo(app_config),
    )
    stereo_btn.pack(pady=5)

    # Make sure closing the window destroys the app.
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
