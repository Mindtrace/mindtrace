from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple, Union

import cv2
import numpy as np
from PIL import Image

from mindtrace.core import pil_to_cv2


@dataclass(frozen=True)
class CalibrationData:
    """Holds homography and camera intrinsics derived or provided during calibration.

    Attributes:
        H: 3x3 homography from world plane (Z=0) in metric units to image pixels
        camera_matrix: 3x3 intrinsics matrix (if known or estimated)
        dist_coeffs: distortion coefficients if available
        world_unit: string describing unit used in world points (e.g., 'mm', 'cm', 'm')
        plane_normal_camera: optional 3D normal of the plane in camera frame if recovered
    """

    H: np.ndarray
    camera_matrix: Optional[np.ndarray] = None
    dist_coeffs: Optional[np.ndarray] = None
    world_unit: str = "mm"
    plane_normal_camera: Optional[np.ndarray] = None


class HomographyCalibrator:
    """Calibrates a planar homography H.

    Calibrates a planar homography H mapping planar world coordinates (X, Y, 1) in metric units to image pixel
    coordinates (u, v, 1) using known point correspondences. Supports checkerboard-based registration.

    Typical flows:
    - Provide planar world points (in chosen unit) and detected image points.
    - Optionally provide camera intrinsics and distortion to undistort first.
    - Optionally estimate intrinsics from FOV and resolution.
    """

    def estimate_intrinsics_from_fov(
        self,
        image_size: Tuple[int, int],
        fov_horizontal_deg: float,
        fov_vertical_deg: float,
        principal_point: Optional[Tuple[float, float]] = None,
    ) -> np.ndarray:
        """Estimate a simple pinhole camera intrinsics matrix from FOV and image size.

        image_size: (width, height)
        returns K (3x3)
        """
        width, height = image_size
        cx = (width - 1) / 2.0
        cy = (height - 1) / 2.0
        if principal_point is not None:
            cx, cy = principal_point

        fx = (width / 2.0) / np.tan(np.deg2rad(fov_horizontal_deg) / 2.0)
        fy = (height / 2.0) / np.tan(np.deg2rad(fov_vertical_deg) / 2.0)

        K = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1.0]], dtype=np.float64)
        return K

    def calibrate_from_correspondences(
        self,
        world_points: np.ndarray,
        image_points: np.ndarray,
        world_unit: str = "mm",
        camera_matrix: Optional[np.ndarray] = None,
        dist_coeffs: Optional[np.ndarray] = None,
    ) -> CalibrationData:
        """Compute homography H given Nx2 world_points (Z=0 plane) in metric units and Nx2 image_points in pixels."""
        world_pts = np.asarray(world_points, dtype=np.float64)
        image_pts = np.asarray(image_points, dtype=np.float64)
        if world_pts.shape[-1] != 2 or image_pts.shape[-1] != 2:
            raise ValueError("world_points and image_points must be Nx2 arrays")
        if world_pts.shape[0] < 4:
            raise ValueError("At least 4 point correspondences are required")
        if image_pts.shape[0] != world_pts.shape[0]:
            raise ValueError("world_points and image_points must have same length")

        undistorted = image_pts
        if camera_matrix is not None and dist_coeffs is not None:
            undistorted = cv2.undistortPoints(
                image_pts.reshape(-1, 1, 2), camera_matrix, dist_coeffs, P=camera_matrix
            ).reshape(-1, 2)

        H, mask = cv2.findHomography(world_pts, undistorted, method=cv2.RANSAC, ransacReprojThreshold=3.0)
        if H is None:
            raise ValueError("Homography estimation failed")

        return CalibrationData(
            H=H,
            camera_matrix=camera_matrix,
            dist_coeffs=dist_coeffs,
            world_unit=world_unit,
        )

    def calibrate_checkerboard(
        self,
        image: Union[Image.Image, np.ndarray],
        board_size: Tuple[int, int],
        square_size: float,
        world_unit: str = "mm",
        camera_matrix: Optional[np.ndarray] = None,
        dist_coeffs: Optional[np.ndarray] = None,
        refine_corners: bool = True,
    ) -> CalibrationData:
        """Detect checkerboard and compute H. The board lies on Z=0 plane.

        Args:
            image: PIL Image or BGR numpy array (i.e. a CV2 image)
            board_size: (cols, rows) inner corners
            square_size: size of one square in world units
            world_unit: unit of the world points
            camera_matrix: camera intrinsics matrix
            dist_coeffs: distortion coefficients
            refine_corners: whether to refine the corners
        """
        # Convert input to CV2 format (BGR numpy array)
        if isinstance(image, Image.Image):
            # PIL Image -> CV2 (BGR)
            cv2_image = pil_to_cv2(image)
        elif isinstance(image, np.ndarray):
            cv2_image = image
        else:
            raise ValueError(f"Unsupported image type: {type(image)}. Expected PIL Image or numpy array.")

        # Convert to grayscale for checkerboard detection
        gray = cv2.cvtColor(cv2_image, cv2.COLOR_BGR2GRAY) if cv2_image.ndim == 3 else cv2_image
        found, corners = cv2.findChessboardCorners(gray, board_size, flags=cv2.CALIB_CB_ADAPTIVE_THRESH)
        if not found:
            raise ValueError("Checkerboard not found")

        if refine_corners:
            criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
            corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)

        cols, rows = board_size
        objp = np.zeros((rows * cols, 2), dtype=np.float64)
        objp[:, 0] = (np.arange(cols).repeat(rows)) * square_size
        objp[:, 1] = (np.tile(np.arange(rows), cols)) * square_size

        return self.calibrate_from_correspondences(
            world_points=objp,
            image_points=corners.reshape(-1, 2),
            world_unit=world_unit,
            camera_matrix=camera_matrix,
            dist_coeffs=dist_coeffs,
        )
