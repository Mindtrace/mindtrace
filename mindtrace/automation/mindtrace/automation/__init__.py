"""
Mindtrace Automation Module

This module provides automation capabilities for quality control (QC) operations
in the Mindtrace system.
"""

from .qc import (
    QC,
    QCJob,
    QCJobDefinition,
    QCJobType,
    QCStatus,
    # Input models
    DataValidationInput,
    ImageSimilarityInput,
    AnomalyDetectionInput,
    CompareModelsInput,
    RunInferenceInput,
    GetResultsInput,
    AddObserverInput,
    DatasetAnalysisInput,
    TrainModelInput,
)

__all__ = [
    "QC",
    "QCJob", 
    "QCJobDefinition",
    "QCJobType",
    "QCStatus",
    "DataValidationInput",
    "ImageSimilarityInput",
    "AnomalyDetectionInput", 
    "CompareModelsInput",
    "RunInferenceInput",
    "GetResultsInput",
    "AddObserverInput",
    "DatasetAnalysisInput",
    "TrainModelInput",
]

__version__ = "0.1.0"
