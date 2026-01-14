"""Homography calibration for planar surface measurement.

This module provides calibration methods for establishing the relationship between
image pixel coordinates and real-world metric coordinates on a planar surface.
"""

from __future__ import annotations

from typing import Optional, Tuple, Union

import cv2
import numpy as np
from PIL import Image

from mindtrace.core import Mindtrace, pil_to_cv2
from mindtrace.hardware.cameras.homography.data import CalibrationData
from mindtrace.hardware.core.config import get_hardware_config
from mindtrace.hardware.core.exceptions import (
    CameraConfigurationError,
    HardwareOperationError,
)


class HomographyCalibrator(Mindtrace):
    """Calibrates planar homography for pixel-to-world coordinate mapping.

    Establishes a homography matrix H that maps planar world coordinates (X, Y, Z=0)
    in metric units to image pixel coordinates (u, v). Supports both automatic
    checkerboard-based calibration and manual point correspondence calibration.

    The homography enables real-world measurements from camera images for objects
    lying on a known planar surface (e.g., overhead cameras, objects on tables/floors).

    Features:
        - Automatic checkerboard pattern detection and calibration
        - Manual point correspondence calibration
        - RANSAC-based robust homography estimation
        - Sub-pixel corner refinement for improved accuracy
        - Lens distortion correction support
        - Camera intrinsics estimation from FOV

    Typical Workflow:
        1. Place calibration target (checkerboard) on measurement plane
        2. Capture image with known world coordinates
        3. Calibrate to obtain homography matrix
        4. Use calibration for repeated measurements

    Usage::

        from mindtrace.hardware import HomographyCalibrator

        # Automatic checkerboard calibration
        calibrator = HomographyCalibrator()
        calibration = calibrator.calibrate_checkerboard(
            image=checkerboard_image,
            board_size=(12, 12),     # Inner corners
            square_width=25.0,       # mm width per square
            square_height=25.0,      # mm height per square
            world_unit="mm"
        )

        # Manual point correspondence calibration
        calibration = calibrator.calibrate_from_correspondences(
            world_points=[(0, 0), (300, 0), (300, 200), (0, 200)],  # mm
            image_points=[(100, 50), (500, 50), (500, 400), (100, 400)],  # pixels
            world_unit="mm"
        )

        # Save for later use
        calibration.save("camera_calibration.json")

    Configuration:
        All parameters can be configured via hardware config:
        - ransac_threshold: RANSAC reprojection error threshold (default: 3.0 pixels)
        - refine_corners: Enable sub-pixel corner refinement (default: True)
        - corner_refinement_window: Refinement window size (default: 11)
        - min_correspondences: Minimum points needed (default: 4)
        - default_world_unit: Default measurement unit (default: "mm")

    Limitations:
        - Only works for planar surfaces (Z=0 assumption)
        - Requires camera to remain fixed after calibration
        - Accuracy degrades with severe viewing angles
    """

    def __init__(self, **kwargs):
        """Initialize homography calibrator.

        Args:
            **kwargs: Additional arguments passed to Mindtrace base class
        """
        super().__init__(**kwargs)

        # Load configuration
        hw_config = get_hardware_config().get_config()
        self._config = hw_config.homography

        self.logger.info(
            f"HomographyCalibrator initialized "
            f"(ransac_threshold={self._config.ransac_threshold}, "
            f"refine_corners={self._config.refine_corners}, "
            f"default_unit={self._config.default_world_unit}, "
            f"default_board={self._config.checkerboard_cols}x{self._config.checkerboard_rows}, "
            f"default_square={self._config.checkerboard_square}{self._config.default_world_unit})"
        )

    def estimate_intrinsics_from_fov(
        self,
        image_size: Tuple[int, int],
        fov_horizontal_deg: float,
        fov_vertical_deg: float,
        principal_point: Optional[Tuple[float, float]] = None,
    ) -> np.ndarray:
        """Estimate camera intrinsics matrix from field-of-view parameters.

        Computes a simple pinhole camera model intrinsics matrix (K) from the
        camera's horizontal and vertical field of view angles and image dimensions.
        Useful when full camera calibration is not available.

        Args:
            image_size: Image dimensions as (width, height) in pixels
            fov_horizontal_deg: Horizontal field of view in degrees
            fov_vertical_deg: Vertical field of view in degrees
            principal_point: Optional (cx, cy) principal point in pixels.
                           Defaults to image center if not provided.

        Returns:
            3x3 camera intrinsics matrix K

        Example::

            K = calibrator.estimate_intrinsics_from_fov(
                image_size=(1920, 1080),
                fov_horizontal_deg=70.0,
                fov_vertical_deg=45.0
            )
        """
        width, height = image_size

        # Default principal point to image center
        cx = (width - 1) / 2.0
        cy = (height - 1) / 2.0
        if principal_point is not None:
            cx, cy = principal_point

        # Compute focal lengths from FOV
        fx = (width / 2.0) / np.tan(np.deg2rad(fov_horizontal_deg) / 2.0)
        fy = (height / 2.0) / np.tan(np.deg2rad(fov_vertical_deg) / 2.0)

        K = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1.0]], dtype=np.float64)

        self.logger.debug(f"Estimated intrinsics from FOV: fx={fx:.2f}, fy={fy:.2f}, cx={cx:.2f}, cy={cy:.2f}")

        return K

    def calibrate_from_correspondences(
        self,
        world_points: np.ndarray,
        image_points: np.ndarray,
        world_unit: Optional[str] = None,
        camera_matrix: Optional[np.ndarray] = None,
        dist_coeffs: Optional[np.ndarray] = None,
    ) -> CalibrationData:
        """Compute homography from known point correspondences.

        Establishes the homography matrix H given known world coordinates (on Z=0 plane)
        and their corresponding image pixel coordinates. Uses RANSAC for robust estimation
        in the presence of outliers.

        Args:
            world_points: Nx2 array of world coordinates in metric units (X, Y on Z=0 plane)
            image_points: Nx2 array of corresponding image coordinates in pixels (u, v)
            world_unit: Unit of world coordinates (e.g., 'mm', 'cm', 'm'). Uses config default if None.
            camera_matrix: Optional 3x3 camera intrinsics matrix for undistortion
            dist_coeffs: Optional distortion coefficients for undistortion

        Returns:
            CalibrationData containing homography matrix and metadata

        Raises:
            CameraConfigurationError: If inputs are invalid (wrong shape, too few points)
            HardwareOperationError: If homography estimation fails

        Example::

            # Four corner correspondences (world in mm, image in pixels)
            world_pts = np.array([[0, 0], [300, 0], [300, 200], [0, 200]])
            image_pts = np.array([[100, 50], [500, 50], [500, 400], [100, 400]])

            calibration = calibrator.calibrate_from_correspondences(
                world_points=world_pts,
                image_points=image_pts,
                world_unit="mm"
            )
        """
        # Use default world unit from config if not provided
        if world_unit is None:
            world_unit = self._config.default_world_unit

        # Validate input arrays
        world_pts = np.asarray(world_points, dtype=np.float64)
        image_pts = np.asarray(image_points, dtype=np.float64)

        if world_pts.shape[-1] != 2 or image_pts.shape[-1] != 2:
            raise CameraConfigurationError("world_points and image_points must be Nx2 arrays")

        if world_pts.shape[0] < self._config.min_correspondences:
            raise CameraConfigurationError(
                f"At least {self._config.min_correspondences} point correspondences are required "
                f"(got {world_pts.shape[0]})"
            )

        if image_pts.shape[0] != world_pts.shape[0]:
            raise CameraConfigurationError("world_points and image_points must have the same number of points")

        self.logger.debug(f"Calibrating from {world_pts.shape[0]} point correspondences (unit={world_unit})")

        # Apply lens distortion correction if camera intrinsics provided
        undistorted = image_pts
        if camera_matrix is not None and dist_coeffs is not None:
            self.logger.debug("Applying lens distortion correction")
            undistorted = cv2.undistortPoints(
                image_pts.reshape(-1, 1, 2), camera_matrix, dist_coeffs, P=camera_matrix
            ).reshape(-1, 2)

        # Compute homography using RANSAC for robustness
        H, mask = cv2.findHomography(
            world_pts, undistorted, method=cv2.RANSAC, ransacReprojThreshold=self._config.ransac_threshold
        )

        if H is None:
            raise HardwareOperationError("Homography estimation failed - unable to find valid transformation")

        # Count inliers
        inlier_count = int(np.sum(mask)) if mask is not None else world_pts.shape[0]
        self.logger.info(
            f"Homography computed successfully ({inlier_count}/{world_pts.shape[0]} inliers, unit={world_unit})"
        )

        return CalibrationData(
            H=H,
            camera_matrix=camera_matrix,
            dist_coeffs=dist_coeffs,
            world_unit=world_unit,
        )

    def _validate_homography_quality(
        self,
        H: np.ndarray,
        image: Optional[np.ndarray] = None,
        board_size: Optional[Tuple[int, int]] = None,
        square_size: Optional[float] = None,
    ) -> Tuple[Optional[float], Optional[float], int]:
        """Validate homography quality and compute reprojection errors.

        Args:
            H: 3x3 homography matrix
            image: Optional calibration image for reprojection error computation
            board_size: Optional checkerboard size (cols, rows) for reprojection validation
            square_size: Optional square size for reprojection validation

        Returns:
            Tuple of (mean_error, max_error, total_corners). Errors are None if validation skipped.

        Raises:
            HardwareOperationError: If homography has invalid determinant
        """
        # Validate determinant
        det = float(np.linalg.det(H))
        abs_det = abs(det)

        # Check for singular matrix (determinant too close to zero)
        if abs_det < 1e-10:
            self.logger.error(f"Invalid homography: determinant too close to zero ({det:.2e})")
            raise HardwareOperationError(f"Calibration failed: singular homography matrix (det={det:.2e})")

        # Warn about suspiciously large determinant magnitude
        if abs_det > 1e10:
            self.logger.warning(
                f"Suspicious homography determinant magnitude: {abs_det:.2e} (may indicate poor calibration)"
            )

        # Note negative determinant (indicates reflection/flip)
        if det < 0:
            self.logger.info(
                f"Homography has negative determinant ({det:.2e}) - indicates coordinate system reflection "
                "(normal for some camera angles)"
            )

        # Compute reprojection error if image and board parameters provided
        mean_error = None
        max_error = None
        total_corners = 0

        if image is not None and board_size is not None and square_size is not None:
            # Convert to grayscale for corner detection
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image

            # Detect checkerboard corners
            found, corners = cv2.findChessboardCorners(gray, board_size)

            if found:
                total_corners = len(corners)

                # Generate world coordinates (row-major order to match OpenCV)
                cols, rows = board_size
                objp = np.zeros((rows * cols, 2), dtype=np.float64)
                objp[:, 0] = (np.tile(np.arange(cols), rows)) * square_size
                objp[:, 1] = (np.arange(rows).repeat(cols)) * square_size

                # Project world points to image using computed homography
                projected = cv2.perspectiveTransform(objp.reshape(-1, 1, 2), H)

                # Compute reprojection errors
                errors = np.linalg.norm(projected.reshape(-1, 2) - corners.reshape(-1, 2), axis=1)
                mean_error = float(np.mean(errors))
                max_error = float(np.max(errors))

                self.logger.info(
                    f"Reprojection error: mean={mean_error:.2f}px, max={max_error:.2f}px (over {total_corners} corners)"
                )

                # Warn if errors are high
                if mean_error > 5.0:
                    self.logger.warning(
                        f"High mean reprojection error ({mean_error:.2f}px) - calibration may be inaccurate"
                    )
                if max_error > 10.0:
                    self.logger.warning(f"High maximum reprojection error ({max_error:.2f}px) - consider recalibrating")

        return mean_error, max_error, total_corners

    def calibrate_checkerboard(
        self,
        image: Union[Image.Image, np.ndarray],
        board_size: Optional[Tuple[int, int]] = None,
        square_size: Optional[float] = None,
        world_unit: Optional[str] = None,
        camera_matrix: Optional[np.ndarray] = None,
        dist_coeffs: Optional[np.ndarray] = None,
        refine_corners: Optional[bool] = None,
    ) -> CalibrationData:
        """Automatic calibration from checkerboard pattern detection.

        Detects a checkerboard calibration pattern in the image, extracts corner
        correspondences, and computes the homography matrix. The checkerboard is
        assumed to lie on the Z=0 plane with known square dimensions.

        Args:
            image: PIL Image or BGR numpy array containing checkerboard pattern
            board_size: Number of inner corners as (columns, rows). Uses config default if None.
                       For a standard 8x8 checkerboard, use (7, 7).
            square_size: Physical size of one checkerboard square in world units. Uses config default if None.
            world_unit: Unit of square_size (e.g., 'mm', 'cm', 'm'). Uses config default if None.
            camera_matrix: Optional 3x3 camera intrinsics matrix for undistortion
            dist_coeffs: Optional distortion coefficients for undistortion
            refine_corners: Enable sub-pixel corner refinement. Uses config default if None.

        Returns:
            CalibrationData containing homography matrix and metadata

        Raises:
            CameraConfigurationError: If image format is unsupported
            HardwareOperationError: If checkerboard detection fails

        Example::

            # Use config defaults for standard calibration board
            calibration = calibrator.calibrate_checkerboard(image=checkerboard_image)

            # Or override specific parameters
            calibration = calibrator.calibrate_checkerboard(
                image=checkerboard_image,
                board_size=(9, 6),         # Custom board size
                square_size=30.0,          # Custom square size
                world_unit="mm"
            )

        Notes:
            - board_size is the number of INNER corners, not squares
            - A standard 8x8 checkerboard has 7x7 inner corners
            - Ensure good lighting and focus for accurate detection
            - Checkerboard should fill significant portion of image
            - If using a standard calibration board, configure dimensions via:
              MINDTRACE_HW_HOMOGRAPHY_CHECKERBOARD_COLS
              MINDTRACE_HW_HOMOGRAPHY_CHECKERBOARD_ROWS
              MINDTRACE_HW_HOMOGRAPHY_CHECKERBOARD_SQUARE
        """
        # Use config defaults if not provided
        if board_size is None:
            board_size = (self._config.checkerboard_cols, self._config.checkerboard_rows)
        if square_size is None:
            square_size = self._config.checkerboard_square
        if world_unit is None:
            world_unit = self._config.default_world_unit
        if refine_corners is None:
            refine_corners = self._config.refine_corners

        self.logger.debug(
            f"Starting checkerboard calibration "
            f"(board_size={board_size}, square={square_size}{world_unit}, "
            f"refine_corners={refine_corners})"
        )

        # Convert input to CV2 format (BGR numpy array)
        if isinstance(image, Image.Image):
            cv2_image = pil_to_cv2(image)
            self.logger.debug("Converted PIL Image to CV2 format")
        elif isinstance(image, np.ndarray):
            cv2_image = image
        else:
            raise CameraConfigurationError(f"Unsupported image type: {type(image)}. Expected PIL Image or numpy array.")

        # Convert to grayscale for checkerboard detection
        gray = cv2.cvtColor(cv2_image, cv2.COLOR_BGR2GRAY) if cv2_image.ndim == 3 else cv2_image

        # Detect checkerboard corners
        flags = 0
        if self._config.checkerboard_adaptive_thresh:
            flags |= cv2.CALIB_CB_ADAPTIVE_THRESH
        if self._config.checkerboard_normalize_image:
            flags |= cv2.CALIB_CB_NORMALIZE_IMAGE
        if self._config.checkerboard_filter_quads:
            flags |= cv2.CALIB_CB_FILTER_QUADS

        self.logger.debug(f"Detecting checkerboard with flags={flags}")
        found, corners = cv2.findChessboardCorners(gray, board_size, flags=flags)

        if not found:
            raise HardwareOperationError(
                f"Checkerboard pattern not found. "
                f"Expected {board_size[0]}x{board_size[1]} inner corners. "
                f"Ensure good lighting, focus, and that the pattern is visible."
            )

        self.logger.debug(f"Checkerboard detected with {len(corners)} corners")

        # Refine corner locations to sub-pixel accuracy
        if refine_corners:
            criteria = (
                cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
                self._config.corner_refinement_iterations,
                self._config.corner_refinement_epsilon,
            )
            window_size = (self._config.corner_refinement_window, self._config.corner_refinement_window)
            corners = cv2.cornerSubPix(gray, corners, window_size, (-1, -1), criteria)
            self.logger.debug(f"Corners refined to sub-pixel accuracy (window={window_size})")

        # Generate world coordinates for checkerboard corners
        # OpenCV returns corners in row-major order (left-to-right, top-to-bottom)
        # so we must generate world points in the same order
        cols, rows = board_size
        objp = np.zeros((rows * cols, 2), dtype=np.float64)
        objp[:, 0] = (np.tile(np.arange(cols), rows)) * square_size  # X: repeat columns for each row
        objp[:, 1] = (np.arange(rows).repeat(cols)) * square_size  # Y: tile rows

        self.logger.debug(f"Generated {len(objp)} world point correspondences")

        # Compute homography from correspondences
        calibration = self.calibrate_from_correspondences(
            world_points=objp,
            image_points=corners.reshape(-1, 2),
            world_unit=world_unit,
            camera_matrix=camera_matrix,
            dist_coeffs=dist_coeffs,
        )

        # Validate homography quality with reprojection error
        self._validate_homography_quality(
            H=calibration.H,
            image=cv2_image,
            board_size=board_size,
            square_size=square_size,
        )

        return calibration

    def calibrate_checkerboard_multi_view(
        self,
        images: list[Union[Image.Image, np.ndarray]],
        positions: list[Tuple[float, float]],
        board_size: Optional[Tuple[int, int]] = None,
        square_width: Optional[float] = None,
        square_height: Optional[float] = None,
        world_unit: Optional[str] = None,
        camera_matrix: Optional[np.ndarray] = None,
        dist_coeffs: Optional[np.ndarray] = None,
        refine_corners: Optional[bool] = None,
    ) -> CalibrationData:
        """Calibrate from multiple checkerboard positions on the same plane.

        Combines corner detections from multiple images where the checkerboard
        is placed at different positions on the measurement plane. This provides
        better calibration coverage over large areas without requiring an
        oversized calibration target.

        Ideal for calibrating long surfaces (e.g., metallic bars, conveyor belts)
        using a standard-sized checkerboard moved to multiple positions.

        Args:
            images: List of images, each containing the checkerboard at a different position
            positions: List of (x_offset, y_offset) tuples in world units specifying
                      the checkerboard's origin position in each image. The first position
                      is typically (0, 0), and subsequent positions indicate how far the
                      checkerboard was moved.
            board_size: Number of inner corners as (columns, rows). Uses config default if None.
            square_width: Physical width of one checkerboard square in world units. Uses config default if None.
            square_height: Physical height of one checkerboard square in world units. Uses config default if None.
            world_unit: Unit of positions and square_width/height. Uses config default if None.
            camera_matrix: Optional 3x3 camera intrinsics matrix for undistortion
            dist_coeffs: Optional distortion coefficients for undistortion
            refine_corners: Enable sub-pixel corner refinement. Uses config default if None.

        Returns:
            CalibrationData containing homography matrix computed from all positions

        Raises:
            CameraConfigurationError: If inputs are invalid or inconsistent
            HardwareOperationError: If checkerboard detection fails in any image

        Example::

            # Calibrate a 2-meter long bar using 3 checkerboard positions
            images = [image1, image2, image3]
            positions = [
                (0, 0),      # Start of bar
                (1000, 0),   # Middle (1000mm from start)
                (2000, 0)    # End (2000mm from start)
            ]

            calibration = calibrator.calibrate_checkerboard_multi_view(
                images=images,
                positions=positions,
                board_size=(12, 12),
                square_width=25.0,    # 25mm wide squares
                square_height=25.0,   # 25mm tall squares
                world_unit="mm"
            )

        Notes:
            - All images must show the same plane (Z=0)
            - Positions specify where the checkerboard origin (top-left corner) is located
            - Use more positions for better coverage of large measurement areas
            - Typical usage: 3-5 positions for long surfaces
            - RANSAC automatically handles slight inaccuracies in position measurements
        """
        # Use config defaults if not provided
        if board_size is None:
            board_size = (self._config.checkerboard_cols, self._config.checkerboard_rows)
        if square_width is None:
            square_width = self._config.checkerboard_square
        if square_height is None:
            square_height = self._config.checkerboard_square
        if world_unit is None:
            world_unit = self._config.default_world_unit
        if refine_corners is None:
            refine_corners = self._config.refine_corners

        # Validate inputs
        if len(images) != len(positions):
            raise CameraConfigurationError(
                f"Number of images ({len(images)}) must match number of positions ({len(positions)})"
            )

        if len(images) < 1:
            raise CameraConfigurationError("At least one image is required for calibration")

        self.logger.info(
            f"Starting multi-view checkerboard calibration "
            f"({len(images)} views, board_size={board_size}, "
            f"square={square_width}x{square_height}{world_unit}, refine_corners={refine_corners})"
        )

        all_world_points = []
        all_image_points = []

        # Process each image and position
        for idx, (image, (x_offset, y_offset)) in enumerate(zip(images, positions)):
            self.logger.debug(
                f"Processing view {idx + 1}/{len(images)} at position ({x_offset}, {y_offset}) {world_unit}"
            )

            # Convert input to CV2 format
            if isinstance(image, Image.Image):
                cv2_image = pil_to_cv2(image)
            elif isinstance(image, np.ndarray):
                cv2_image = image
            else:
                raise CameraConfigurationError(
                    f"View {idx + 1}: Unsupported image type: {type(image)}. Expected PIL Image or numpy array."
                )

            # Convert to grayscale
            gray = cv2.cvtColor(cv2_image, cv2.COLOR_BGR2GRAY) if cv2_image.ndim == 3 else cv2_image

            # Detect checkerboard corners
            flags = 0
            if self._config.checkerboard_adaptive_thresh:
                flags |= cv2.CALIB_CB_ADAPTIVE_THRESH
            if self._config.checkerboard_normalize_image:
                flags |= cv2.CALIB_CB_NORMALIZE_IMAGE
            if self._config.checkerboard_filter_quads:
                flags |= cv2.CALIB_CB_FILTER_QUADS

            found, corners = cv2.findChessboardCorners(gray, board_size, flags=flags)

            if not found:
                raise HardwareOperationError(
                    f"View {idx + 1}: Checkerboard pattern not found. "
                    f"Expected {board_size[0]}x{board_size[1]} inner corners. "
                    f"Ensure good lighting, focus, and that the pattern is visible."
                )

            self.logger.debug(f"View {idx + 1}: Detected {len(corners)} corners")

            # Refine corner locations to sub-pixel accuracy
            if refine_corners:
                criteria = (
                    cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
                    self._config.corner_refinement_iterations,
                    self._config.corner_refinement_epsilon,
                )
                window_size = (self._config.corner_refinement_window, self._config.corner_refinement_window)
                corners = cv2.cornerSubPix(gray, corners, window_size, (-1, -1), criteria)
                self.logger.debug(f"View {idx + 1}: Corners refined to sub-pixel accuracy")

            # Generate world coordinates for this checkerboard position (row-major order to match OpenCV)
            # Supports rectangular checkerboards: width != height
            cols, rows = board_size
            objp = np.zeros((rows * cols, 2), dtype=np.float64)
            objp[:, 0] = (np.tile(np.arange(cols), rows)) * square_width + x_offset  # X coordinates (width)
            objp[:, 1] = (np.arange(rows).repeat(cols)) * square_height + y_offset  # Y coordinates (height)

            all_world_points.append(objp)
            all_image_points.append(corners.reshape(-1, 2))

        # Combine all correspondences from all views
        combined_world_points = np.vstack(all_world_points)
        combined_image_points = np.vstack(all_image_points)

        total_points = combined_world_points.shape[0]
        self.logger.info(
            f"Combined {total_points} point correspondences from {len(images)} views "
            f"(avg {total_points // len(images)} per view)"
        )

        # Compute homography from all combined correspondences
        return self.calibrate_from_correspondences(
            world_points=combined_world_points,
            image_points=combined_image_points,
            world_unit=world_unit,
            camera_matrix=camera_matrix,
            dist_coeffs=dist_coeffs,
        )
