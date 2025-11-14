"""Homography Calibration & Measurement TaskSchemas."""

from mindtrace.core import TaskSchema
from mindtrace.hardware.api.cameras.models import (
    HomographyBatchMeasurementResponse,
    HomographyCalibrateCheckerboardRequest,
    HomographyCalibrateCorrespondencesRequest,
    HomographyCalibrateMultiViewRequest,
    HomographyCalibrationResponse,
    HomographyDistanceResponse,
    HomographyMeasureBatchRequest,
    HomographyMeasureBoundingBoxRequest,
    HomographyMeasureDistanceRequest,
    HomographyMeasurementResponse,
)

# Homography Calibration Schemas
CalibrateHomographyCheckerboardSchema = TaskSchema(
    name="calibrate_homography_checkerboard",
    input_schema=HomographyCalibrateCheckerboardRequest,
    output_schema=HomographyCalibrationResponse,
)

CalibrateHomographyCorrespondencesSchema = TaskSchema(
    name="calibrate_homography_correspondences",
    input_schema=HomographyCalibrateCorrespondencesRequest,
    output_schema=HomographyCalibrationResponse,
)

CalibrateHomographyMultiViewSchema = TaskSchema(
    name="calibrate_homography_multi_view",
    input_schema=HomographyCalibrateMultiViewRequest,
    output_schema=HomographyCalibrationResponse,
)

# Homography Measurement Schemas
MeasureHomographyBoxSchema = TaskSchema(
    name="measure_homography_box",
    input_schema=HomographyMeasureBoundingBoxRequest,
    output_schema=HomographyMeasurementResponse,
)

MeasureHomographyBatchSchema = TaskSchema(
    name="measure_homography_batch",
    input_schema=HomographyMeasureBatchRequest,
    output_schema=HomographyBatchMeasurementResponse,
)

MeasureHomographyDistanceSchema = TaskSchema(
    name="measure_homography_distance",
    input_schema=HomographyMeasureDistanceRequest,
    output_schema=HomographyDistanceResponse,
)

__all__ = [
    "CalibrateHomographyCheckerboardSchema",
    "CalibrateHomographyCorrespondencesSchema",
    "CalibrateHomographyMultiViewSchema",
    "MeasureHomographyBoxSchema",
    "MeasureHomographyBatchSchema",
    "MeasureHomographyDistanceSchema",
]
