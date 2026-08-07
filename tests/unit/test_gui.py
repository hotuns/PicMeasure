"""Unit tests for the graphical file-selection launcher."""

from __future__ import annotations

from pathlib import Path

import pytest

from picmeasure.config import AppConfig
from picmeasure.gui import _run_monocular, _run_stereo


@pytest.mark.unit
def test_run_monocular_forwards_selected_files(
    monkeypatch: pytest.MonkeyPatch,
    synthetic_ball_path: Path,
    tmp_path: Path,
) -> None:
    """Monocular GUI path forwards selected files to measure_clicks."""
    output_path = tmp_path / "mono.json"

    def fake_askopenfilename(*, title, filetypes):
        if "选择要测量的图像" in title:
            return str(synthetic_ball_path)
        return None

    def fake_asksaveasfilename(*, title, defaultextension, filetypes):
        return str(output_path)

    monkeypatch.setattr("tkinter.filedialog.askopenfilename", fake_askopenfilename)
    monkeypatch.setattr("tkinter.filedialog.asksaveasfilename", fake_asksaveasfilename)
    monkeypatch.setattr("tkinter.messagebox.showinfo", lambda *a, **k: None)
    monkeypatch.setattr("tkinter.messagebox.showerror", lambda *a, **k: None)

    calls = []

    def fake_measure_clicks(image, output, app_config, annotated_path=None):
        calls.append(("measure", image, output))

    monkeypatch.setattr("picmeasure.gui._measure_clicks", fake_measure_clicks)

    _run_monocular(AppConfig())

    assert len(calls) == 1
    assert calls[0][0] == "measure"
    assert calls[0][1] == synthetic_ball_path
    assert calls[0][2] == output_path


@pytest.mark.unit
def test_run_stereo_forwards_selected_files(
    monkeypatch: pytest.MonkeyPatch,
    stereo_config,
    synthetic_stereo_pair,
    tmp_path: Path,
) -> None:
    """Stereo GUI path forwards selected files to stereo_measure_clicks."""
    left_path, right_path, _ = synthetic_stereo_pair
    stereo_toml = tmp_path / "stereo.toml"
    stereo_toml.write_text(
        "[stereo]\n"
        "enabled = true\n"
        "focal_length_px = 800.0\n"
        "principal_point = [320.0, 240.0]\n"
        "rotation = [[1.0,0.0,0.0],[0.0,1.0,0.0],[0.0,0.0,1.0]]\n"
        "translation = [10.0, 0.0, 0.0]\n"
        "baseline = 10.0\n"
        'unit = "cm"\n'
    )
    output_path = tmp_path / "stereo.json"

    dialog_sequence = {
        "选择左相机图像": str(left_path),
        "选择右相机图像": str(right_path),
        "选择双目标定 TOML 文件": str(stereo_toml),
    }

    def fake_askopenfilename(*, title, filetypes):
        return dialog_sequence.get(title)

    def fake_asksaveasfilename(*, title, defaultextension, filetypes):
        return str(output_path)

    monkeypatch.setattr("tkinter.filedialog.askopenfilename", fake_askopenfilename)
    monkeypatch.setattr("tkinter.filedialog.asksaveasfilename", fake_asksaveasfilename)
    monkeypatch.setattr("tkinter.messagebox.showinfo", lambda *a, **k: None)
    monkeypatch.setattr("tkinter.messagebox.showerror", lambda *a, **k: None)

    calls = []

    def fake_stereo_measure(left, right, output, app_config, annotated_path=None):
        calls.append(("stereo", left, right, output, app_config.stereo.enabled))

    monkeypatch.setattr("picmeasure.gui.stereo_measure_clicks", fake_stereo_measure)

    _run_stereo(AppConfig())

    assert len(calls) == 1
    assert calls[0][0] == "stereo"
    assert calls[0][1] == left_path
    assert calls[0][2] == right_path
    assert calls[0][3] == output_path
    assert calls[0][4] is True
