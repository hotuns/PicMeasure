"""JSON persistence for stereo measurement results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from picmeasure.stereo.models import StereoMeasurementFile


def save_stereo_measurements(sm: StereoMeasurementFile, output_path: Path) -> None:
    """Persist a stereo measurement file as JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def _ball_dict(b):
        if b is None:
            return None
        return {
            "detected": b.detected,
            "pixels_per_unit": b.pixels_per_unit,
            "ball_center_xy": list(b.ball_center_xy) if b.ball_center_xy else None,
            "ball_radius_px": b.ball_radius_px,
            "confidence": b.confidence,
            "error_message": b.error_message,
            "source": b.source,
            "candidate_score": b.candidate_score,
        }

    payload = {
        "schema_version": 2,
        "mode": "stereo",
        "images": {"left": sm.left_image_path, "right": sm.right_image_path},
        "unit": sm.unit,
        "stereo": {
            "baseline_units": sm.baseline_units,
            "baseline_unit": sm.unit,
            "focal_length_px": sm.focal_length_px,
            "principal_point": list(sm.principal_point),
            "rotation": sm.rotation,
            "translation": sm.translation,
            "distortion_coefficients": sm.distortion_coefficients,
            "reprojection_error_px": sm.reprojection_error_px,
        },
        "scale_check": {
            "left_ball": _ball_dict(sm.left_ball),
            "right_ball": _ball_dict(sm.right_ball),
            "triangulated_ball_diameter_units": sm.triangulated_ball_diameter_units,
        },
        "branches": [
            {
                "branch_id": b.branch_id,
                "vertices_left": [list(v) for v in b.vertices_left],
                "vertices_right": [list(v) for v in b.vertices_right],
                "vertices_3d": [
                    [round(v.x, 3), round(v.y, 3), round(v.z, 3)] for v in b.vertices_3d
                ],
                "length_units": round(b.length_units, 2),
                "unit": b.unit,
                "diameter_measurements": [
                    {
                        "section_id": d.section_id,
                        "edges_left": [list(v) for v in d.edges_left],
                        "edges_right": [list(v) for v in d.edges_right],
                        "edges_3d": [
                            [round(v.x, 3), round(v.y, 3), round(v.z, 3)] for v in d.edges_3d
                        ],
                        "diameter_units": round(d.diameter_units, 2),
                        "unit": d.unit,
                    }
                    for d in b.diameter_measurements
                ],
            }
            for b in sm.branches
            if b.vertices_left or b.diameter_measurements
        ],
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_stereo_measurements(path: Path) -> StereoMeasurementFile:
    """Load a stereo measurement file from JSON."""
    from picmeasure.ball.models import BallDetectionResult
    from picmeasure.stereo.geometry import Point3D
    from picmeasure.stereo.models import (
        StereoBranch,
        StereoDiameterMeasurement,
        StereoMeasurementFile,
    )

    data = json.loads(path.read_text(encoding="utf-8"))
    stereo = data.get("stereo", {})
    scale = data.get("scale_check", {})

    def load_ball(raw: dict | None) -> BallDetectionResult | None:
        if not raw:
            return None
        center = raw.get("ball_center_xy")
        return BallDetectionResult(
            detected=bool(raw.get("detected", False)),
            pixels_per_unit=raw.get("pixels_per_unit"),
            ball_center_xy=tuple(center) if center else None,  # type: ignore[arg-type]
            ball_radius_px=raw.get("ball_radius_px"),
            confidence=raw.get("confidence"),
            error_message=raw.get("error_message"),
            source=str(raw.get("source", "auto")),
            candidate_score=raw.get("candidate_score"),
        )

    branches = []
    for raw in data.get("branches", []):
        verts_3d = [Point3D(*v) for v in raw.get("vertices_3d", [])]
        diameters = []
        for diameter in raw.get("diameter_measurements", []):
            left = diameter.get("edges_left", [[0, 0], [0, 0]])
            right = diameter.get("edges_right", [[0, 0], [0, 0]])
            points_3d = tuple(Point3D(*v) for v in diameter.get("edges_3d", []))
            if len(points_3d) == 2:
                diameters.append(
                    StereoDiameterMeasurement(
                        section_id=int(diameter["section_id"]),
                        edges_left=(tuple(left[0]), tuple(left[1])),  # type: ignore[arg-type]
                        edges_right=(tuple(right[0]), tuple(right[1])),  # type: ignore[arg-type]
                        edges_3d=points_3d,  # type: ignore[arg-type]
                        diameter_units=float(diameter.get("diameter_units", 0.0)),
                        unit=str(diameter.get("unit", data.get("unit", "cm"))),
                    )
                )
        branches.append(
            StereoBranch(
                branch_id=int(raw["branch_id"]),
                vertices_left=[tuple(v) for v in raw.get("vertices_left", [])],
                vertices_right=[tuple(v) for v in raw.get("vertices_right", [])],
                vertices_3d=verts_3d,
                length_units=float(raw.get("length_units", 0.0)),
                unit=str(raw.get("unit", data.get("unit", "cm"))),
                diameter_measurements=diameters,
            )
        )

    return StereoMeasurementFile(
        left_image_path=str(data.get("images", {}).get("left", data.get("left_image_path", ""))),
        right_image_path=str(data.get("images", {}).get("right", data.get("right_image_path", ""))),
        unit=str(data.get("unit", "cm")),
        baseline_units=float(stereo.get("baseline_units", 0.0)),
        focal_length_px=float(stereo.get("focal_length_px", 0.0)),
        principal_point=tuple(stereo.get("principal_point", [0.0, 0.0])),
        rotation=stereo.get("rotation", [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]),
        translation=stereo.get("translation", [0.0, 0.0, 0.0]),
        distortion_coefficients=stereo.get("distortion_coefficients", [0.0, 0.0, 0.0, 0.0, 0.0]),
        reprojection_error_px=stereo.get("reprojection_error_px"),
        left_ball=load_ball(scale.get("left_ball")),
        right_ball=load_ball(scale.get("right_ball")),
        triangulated_ball_diameter_units=scale.get("triangulated_ball_diameter_units"),
        branches=branches,
    )
