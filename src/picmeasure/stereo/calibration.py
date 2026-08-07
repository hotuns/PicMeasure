"""Stereo calibration: build rectification maps from StereoConfig."""

from __future__ import annotations

import logging

import cv2
import numpy as np
import numpy.typing as npt

from picmeasure.config import StereoConfig
from picmeasure.stereo.models import RectificationMaps, StereoCalibration

logger = logging.getLogger(__name__)


def calibration_from_config(
    config: StereoConfig,
    image_size: tuple[int, int],
) -> StereoCalibration:
    """Build a normalized ``StereoCalibration`` from pydantic config."""
    k = config.camera_matrix_array("left")
    k2 = config.camera_matrix_array("right")
    d = config.distortion_array("left")
    d2 = config.distortion_array("right")

    def pad_distortion(values: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        if values.size >= 5:
            return values
        padded = np.zeros(5, dtype=np.float64)
        padded[: values.size] = values
        return padded

    d = pad_distortion(d)
    d2 = pad_distortion(d2)
    r = config.rotation_array()
    t = config.translation_array()
    return StereoCalibration(
        k=k,
        d=d,
        k2=k2,
        d2=d2,
        r=r,
        t=t,
        image_size=image_size,
        baseline_units=config.baseline_units,
        unit=config.unit,
        alpha=config.alpha,
    )


def build_rectification(
    calib: StereoCalibration,
) -> RectificationMaps:
    """Compute rectification maps for a calibrated stereo rig.

    Uses ``cv2.stereoRectify`` and ``cv2.initUndistortRectifyMap`` with
    independent intrinsics for the left and right cameras.
    """
    width, height = calib.image_size
    image_size_cv = (width, height)
    translation_cv = calib.t.reshape(3, 1)

    r1, r2, p1, p2, q, roi1, roi2 = cv2.stereoRectify(
        cameraMatrix1=calib.k,
        distCoeffs1=calib.d,
        cameraMatrix2=calib.k2,
        distCoeffs2=calib.d2,
        imageSize=image_size_cv,
        R=calib.r,
        T=translation_cv,
        flags=cv2.CALIB_ZERO_DISPARITY,
        alpha=calib.alpha,
        newImageSize=image_size_cv,
    )

    map1x, map1y = cv2.initUndistortRectifyMap(
        calib.k, calib.d, r1, p1, image_size_cv, cv2.CV_32FC1
    )
    map2x, map2y = cv2.initUndistortRectifyMap(
        calib.k2, calib.d2, r2, p2, image_size_cv, cv2.CV_32FC1
    )

    logger.debug(
        "Rectified stereo pair: image_size=%s, P1[0,0]=%.2f, baseline=%.2f %s",
        image_size_cv,
        float(p1[0, 0]),
        calib.baseline_units,
        calib.unit,
    )

    return RectificationMaps(
        r1=r1,
        r2=r2,
        p1=p1,
        p2=p2,
        q=q,
        map1x=map1x,
        map1y=map1y,
        map2x=map2x,
        map2y=map2y,
        roi1=roi1,
        roi2=roi2,
    )


def rectify_image(
    image: npt.NDArray[np.uint8],
    map_x: npt.NDArray[np.float32],
    map_y: npt.NDArray[np.float32],
) -> npt.NDArray[np.uint8]:
    """Apply OpenCV remap to produce a rectified image."""
    return cv2.remap(image, map_x, map_y, cv2.INTER_LINEAR)
