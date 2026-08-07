"""Typer CLI entry point for picmeasure.

Commands:
    * ``calibrate`` — detect the reference ball and print pixels-per-unit.
    * ``click-measure`` — monocular interactive picker using the ball scale.
    * ``stereo-calibrate`` — validate a binocular stereo rig.
    * ``stereo-measure`` — binocular interactive picker with auto epipolar matching.
"""

from __future__ import annotations

import json
import logging
import threading
import webbrowser
from pathlib import Path

import cv2
import numpy as np
import typer

from picmeasure.ball.detector import BallDetector
from picmeasure.clickmeasure.picker import measure_clicks as _measure_clicks
from picmeasure.config import AppConfig, StereoConfig, setup_logging
from picmeasure.gui import launch_gui
from picmeasure.stereo.calibration import (
    build_rectification,
    calibration_from_config,
    rectify_image,
)
from picmeasure.stereo.geometry import triangulate_rectified
from picmeasure.stereo.models import CalibrationReport
from picmeasure.stereo.picker import stereo_measure_clicks

app = typer.Typer(help="PicMeasure - Tree branch length measurement via reference ball")
logger = logging.getLogger(__name__)


@app.callback()  # type: ignore[untyped-decorator]
def main() -> None:
    """PicMeasure CLI entry point."""
    pass


def _load_config(config_path: Path) -> AppConfig:
    """Load AppConfig from TOML or return defaults if file is missing."""
    if config_path.exists():
        return AppConfig.from_toml(config_path)
    return AppConfig()


def _load_stereo_config(stereo_config_path: Path) -> StereoConfig:
    """Load StereoConfig from a dedicated TOML file."""
    if not stereo_config_path.exists():
        raise typer.BadParameter(f"Stereo config file not found: {stereo_config_path}")
    data = AppConfig.from_toml(stereo_config_path)
    return data.stereo


@app.command()  # type: ignore[untyped-decorator]
def calibrate(
    image: Path = typer.Argument(..., help="Input image file path", exists=True),
    config: Path = typer.Option(Path("config.toml"), "--config", help="Configuration TOML file"),
    unit: str | None = typer.Option(None, "--unit", help="Override output unit (mm|cm)"),
    verbose: bool = typer.Option(False, "--verbose", help="Enable debug output"),
) -> None:
    """Run only reference-ball detection / calibration on an image."""
    app_config = _load_config(config)
    if verbose:
        app_config.logging.level = "DEBUG"
    setup_logging(app_config.logging)

    out_unit = unit if unit in ("mm", "cm") else app_config.output_unit

    detector = BallDetector(app_config.ball)
    img = cv2.imread(str(image))
    if img is None:
        typer.echo(
            json.dumps({"detected": False, "error_message": f"Could not load image: {image}"})
        )
        raise typer.Exit(code=1)

    result = detector.detect(img)

    output = {
        "detected": result.detected,
        "pixels_per_unit": (
            result.pixels_per_unit / 10.0
            if result.pixels_per_unit is not None and out_unit == "mm"
            else result.pixels_per_unit
        ),
        "unit": out_unit,
        "ball_center_xy": result.ball_center_xy,
        "ball_radius_px": result.ball_radius_px,
        "confidence": result.confidence,
        "error_message": result.error_message,
    }
    typer.echo(json.dumps(output, indent=2))

    if not result.detected:
        raise typer.Exit(code=1)


@app.command(name="click-measure")  # type: ignore[untyped-decorator]
def click_measure_cmd(
    image: Path = typer.Argument(..., help="Image file to measure on", exists=True),
    output: Path = typer.Option(..., "--output", "-o", help="Path to write measurement JSON"),
    config: Path = typer.Option(Path("config.toml"), "--config", help="Configuration TOML file"),
    annotated: Path | None = typer.Option(
        None,
        "--annotated",
        help="Path for the annotated image; defaults to <output_stem>_annotated.jpg",
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Enable debug output"),
) -> None:
    """Calibrate via the orange ball, then click polylines to measure branches.

    The reference ball is detected once and gives px-per-unit. Every left
    click adds a vertex to the current branch's polyline; the running
    length (in the configured output unit) is shown live. Right click or
    'n' finishes the current branch and starts a new one. 's' saves both
    a JSON of all measurements and an annotated image; 'q' quits without
    saving.
    """
    app_config = _load_config(config)
    if verbose:
        app_config.logging.level = "DEBUG"
    setup_logging(app_config.logging)
    _measure_clicks(image, output, app_config=app_config, annotated_path=annotated)


@app.command(name="stereo-calibrate")  # type: ignore[untyped-decorator]
def stereo_calibrate_cmd(
    left: Path = typer.Argument(..., help="Left camera image", exists=True),
    right: Path = typer.Argument(..., help="Right camera image", exists=True),
    stereo_config: Path = typer.Option(
        ..., "--stereo-config", help="TOML file with [stereo] calibration parameters"
    ),
    config: Path = typer.Option(
        Path("config.toml"), "--config", help="Main configuration TOML file"
    ),
    unit: str | None = typer.Option(None, "--unit", help="Override output unit (mm|cm)"),
    verbose: bool = typer.Option(False, "--verbose", help="Enable debug output"),
) -> None:
    """Validate a binocular stereo rig and optionally triangulate the reference ball.

    Loads the stereo calibration (K, R, T, baseline), rectifies the image pair,
    detects the orange ball in both views, and reports the rectified scale.
    """
    app_config = _load_config(config)
    if verbose:
        app_config.logging.level = "DEBUG"
    setup_logging(app_config.logging)

    stereo_cfg = _load_stereo_config(stereo_config)
    if not stereo_cfg.enabled:
        stereo_cfg.enabled = True

    out_unit = unit if unit in ("mm", "cm") else app_config.output_unit

    left_bgr = cv2.imread(str(left))
    right_bgr = cv2.imread(str(right))
    if left_bgr is None or right_bgr is None:
        typer.echo(json.dumps({"rectified": False, "message": "Could not load images"}))
        raise typer.Exit(code=1)

    h, w = left_bgr.shape[:2]
    calibration = calibration_from_config(stereo_cfg, (w, h))
    try:
        rect_maps = build_rectification(calibration)
    except cv2.error as exc:
        logger.exception("Rectification failed")
        typer.echo(json.dumps({"rectified": False, "message": f"Rectification failed: {exc}"}))
        raise typer.Exit(code=1) from exc

    rect_left = rectify_image(left_bgr, rect_maps.map1x, rect_maps.map1y)
    rect_right = rectify_image(right_bgr, rect_maps.map2x, rect_maps.map2y)

    detector = BallDetector(app_config.ball)
    left_ball = detector.detect(rect_left)
    right_ball = detector.detect(rect_right)

    triangulated_diameter: float | None = None
    reproj_error: float | None = None
    if (
        left_ball.detected
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
            triangulated_diameter = 2.0 * pt3d.z
            # Reprojection sanity check.
            p_hom = np.append(pt3d.array(), 1.0)
            pl = rect_maps.p1 @ p_hom
            pr = rect_maps.p2 @ p_hom
            pl = pl[:2] / pl[2]
            pr = pr[:2] / pr[2]
            err_l = float(np.linalg.norm(pl - np.array(left_ball.ball_center_xy)))
            err_r = float(np.linalg.norm(pr - np.array(right_ball.ball_center_xy)))
            reproj_error = (err_l + err_r) / 2.0
        except ValueError as exc:
            logger.warning("Ball triangulation failed: %s", exc)

    report = CalibrationReport(
        rectified=True,
        image_size=(w, h),
        baseline_units=calibration.baseline_units,
        baseline_unit=out_unit,
        focal_length_px=float(rect_maps.p1[0, 0]),
        principal_point=(float(rect_maps.p1[0, 2]), float(rect_maps.p1[1, 2])),
        left_ball=left_ball,
        right_ball=right_ball,
        triangulated_ball_diameter_units=triangulated_diameter,
        reprojection_error_px=reproj_error,
        message="Stereo rig validated",
    )
    typer.echo(json.dumps(report.to_dict(), indent=2))


@app.command(name="stereo-measure")  # type: ignore[untyped-decorator]
def stereo_measure_cmd(
    left: Path = typer.Argument(..., help="Left camera image", exists=True),
    right: Path = typer.Argument(..., help="Right camera image", exists=True),
    output: Path = typer.Option(..., "--output", "-o", help="Path to write measurement JSON"),
    stereo_config: Path = typer.Option(
        ..., "--stereo-config", help="TOML file with [stereo] calibration parameters"
    ),
    config: Path = typer.Option(
        Path("config.toml"), "--config", help="Main configuration TOML file"
    ),
    annotated: Path | None = typer.Option(
        None,
        "--annotated",
        help="Path for the annotated side-by-side image; defaults to <output_stem>_annotated.jpg",
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Enable debug output"),
) -> None:
    """Measure branch lengths using binocular stereo.

    Rectifies the image pair using the supplied calibration, then opens an
    interactive two-pane picker. Click on the left image to add vertices; the
    corresponding right-image point is found automatically along the epipolar
    line. Press 'm' to toggle manual mode (click left then right). 's' saves
    the JSON and an annotated image; 'q' quits without saving.
    """
    app_config = _load_config(config)
    if verbose:
        app_config.logging.level = "DEBUG"
    setup_logging(app_config.logging)

    stereo_cfg = _load_stereo_config(stereo_config)
    if not stereo_cfg.enabled:
        stereo_cfg.enabled = True
    app_config.stereo = stereo_cfg

    stereo_measure_clicks(left, right, output, app_config=app_config, annotated_path=annotated)


@app.command(name="gui")  # type: ignore[untyped-decorator]
def gui_cmd(
    config: Path = typer.Option(Path("config.toml"), "--config", help="Configuration TOML file"),
    verbose: bool = typer.Option(False, "--verbose", help="Enable debug output"),
) -> None:
    """Launch the browser-based measurement workbench.

    Choose between single-image (ball + click) measurement or binocular
    stereo measurement. All file paths are selected via native dialogs.
    """
    # ``web_cmd`` is also a Typer callback, so calling it directly must pass
    # concrete values instead of its ``OptionInfo`` default objects.
    web_cmd(
        config=config,
        verbose=verbose,
        host="127.0.0.1",
        port=8765,
        no_open=False,
    )


@app.command(name="legacy-gui")  # type: ignore[untyped-decorator]
def legacy_gui_cmd(
    config: Path = typer.Option(Path("config.toml"), "--config", help="Configuration TOML file"),
    verbose: bool = typer.Option(False, "--verbose", help="Enable debug output"),
) -> None:
    """Launch the previous Tkinter and Matplotlib interface."""
    app_config = _load_config(config)
    if verbose:
        app_config.logging.level = "DEBUG"
    setup_logging(app_config.logging)
    launch_gui(app_config)


@app.command(name="web")  # type: ignore[untyped-decorator]
def web_cmd(
    config: Path = typer.Option(Path("config.toml"), "--config", help="Configuration TOML file"),
    verbose: bool = typer.Option(False, "--verbose", help="Enable debug output"),
    host: str = typer.Option("127.0.0.1", "--host", help="Local bind address"),
    port: int = typer.Option(8765, "--port", help="Local port"),
    no_open: bool = typer.Option(False, "--no-open", help="Do not open a browser automatically"),
) -> None:
    """Run the local PicMeasure web application."""
    import uvicorn

    app_config = _load_config(config)
    if verbose:
        app_config.logging.level = "DEBUG"
    setup_logging(app_config.logging)
    url = f"http://{host}:{port}"
    if not no_open:
        threading.Timer(0.8, webbrowser.open, args=(url,)).start()
    uvicorn.run("picmeasure.web:app", host=host, port=port, reload=False)
