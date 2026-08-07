"""3D stereo geometry utilities: triangulation, polyline length, projection."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True)
class Point3D:
    """A 3D point in the left-camera coordinate frame."""

    x: float
    y: float
    z: float

    def array(self) -> npt.NDArray[np.float64]:
        return np.array([self.x, self.y, self.z], dtype=np.float64)


def triangulate_rectified(
    left_pt: tuple[float, float],
    right_pt: tuple[float, float],
    p1: npt.NDArray[np.float64],
    p2: npt.NDArray[np.float64],
) -> Point3D:
    """Triangulate a 3D point from a matched pair on rectified images.

    For a rectified stereo pair the projection matrices have the form::

        P1 = [[f, 0, cx, 0], [0, f, cy, 0], [0, 0, 1, 0]]
        P2 = [[f, 0, cx, -f*B], [0, f, cy, 0], [0, 0, 1, 0]]

    where ``B`` is the baseline. The disparity is ``d = x_l - x_r`` and::

        Z = f * B / d
        X = (x_l - cx) * Z / f
        Y = (y_l - cy) * Z / f

    Args:
        left_pt: (x, y) in the rectified left image.
        right_pt: (x, y) in the rectified right image; must share the same y.
        p1: 3x4 left projection matrix.
        p2: 3x4 right projection matrix.

    Returns:
        The reconstructed 3D point in the left-camera coordinate frame.

    Raises:
        ValueError: If the disparity is non-positive or the projection matrices
            are not in the expected rectified form.
    """
    xl, yl = (float(v) for v in left_pt)
    xr, yr = (float(v) for v in right_pt)

    f = float(p1[0, 0])
    cx = float(p1[0, 2])
    cy = float(p1[1, 2])
    if f <= 0:
        raise ValueError("invalid focal length in projection matrix")

    baseline = abs(float(p2[0, 3])) / f
    if baseline <= 0:
        raise ValueError("could not derive positive baseline from P2")

    d = xl - xr
    if abs(d) < 1e-6:
        raise ValueError(f"disparity too small ({d}); point is at infinity or mismatched")

    z = f * baseline / d
    x = (xl - cx) * z / f
    y = (yl - cy) * z / f
    return Point3D(x=x, y=y, z=z)


def triangulate_dlt(
    left_pt: tuple[float, float],
    right_pt: tuple[float, float],
    p1: npt.NDArray[np.float64],
    p2: npt.NDArray[np.float64],
) -> Point3D:
    """Triangulate using the Direct Linear Transform (DLT).

    This is a fallback for non-rectified or general stereo rigs. It solves
    the homogeneous linear system A X = 0 via SVD.
    """
    x1, y1 = (float(v) for v in left_pt)
    x2, y2 = (float(v) for v in right_pt)

    a = np.zeros((4, 4), dtype=np.float64)
    a[0] = x1 * p1[2] - p1[0]
    a[1] = y1 * p1[2] - p1[1]
    a[2] = x2 * p2[2] - p2[0]
    a[3] = y2 * p2[2] - p2[1]

    _, _, vt = np.linalg.svd(a)
    x = vt[-1]
    x /= x[3]
    return Point3D(x=float(x[0]), y=float(x[1]), z=float(x[2]))


def polyline_length_3d(vertices: list[Point3D]) -> float:
    """Sum the Euclidean lengths of a 3D polyline's segments."""
    if len(vertices) < 2:
        return 0.0
    total = 0.0
    for i in range(len(vertices) - 1):
        a = vertices[i].array()
        b = vertices[i + 1].array()
        total += float(np.linalg.norm(b - a))
    return total


def project_point(
    point_3d: npt.NDArray[np.float64],
    camera_matrix: npt.NDArray[np.float64],
    rotation: npt.NDArray[np.float64] | None = None,
    translation: npt.NDArray[np.float64] | None = None,
) -> tuple[float, float]:
    """Project a 3D point to a 2D image coordinate using K, R, T.

    If ``rotation``/``translation`` are omitted the point is assumed to be
    in the camera coordinate frame (left camera).
    """
    pt = np.asarray(point_3d, dtype=np.float64).reshape(3)
    if rotation is not None and translation is not None:
        pt = rotation @ pt + translation
    if pt[2] <= 0:
        raise ValueError("point is behind the camera")
    projected = camera_matrix @ pt
    x = projected[0] / projected[2]
    y = projected[1] / projected[2]
    return float(x), float(y)


def reprojection_error(
    point_3d: Point3D,
    left_pt: tuple[float, float],
    right_pt: tuple[float, float],
    left_proj: npt.NDArray[np.float64],
    right_proj: npt.NDArray[np.float64],
) -> float:
    """Mean reprojection error (pixels) for a triangulated 3D point."""
    p = point_3d.array()
    p_hom = np.append(p, 1.0)

    pl = left_proj @ p_hom
    pl = pl[:2] / pl[2]
    pr = right_proj @ p_hom
    pr = pr[:2] / pr[2]

    err_l = math.hypot(pl[0] - left_pt[0], pl[1] - left_pt[1])
    err_r = math.hypot(pr[0] - right_pt[0], pr[1] - right_pt[1])
    return float((err_l + err_r) / 2.0)
