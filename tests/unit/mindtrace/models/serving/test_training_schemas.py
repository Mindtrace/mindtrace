"""Unit tests for `mindtrace.models.serving.training_schemas`."""

from __future__ import annotations

import pytest

from mindtrace.models.serving.training_schemas import (
    ClassifierTrainRequest,
    DetectorTrainRequest,
    SegmenterTrainRequest,
    TrainJobResponse,
    TrainJobStatus,
    TrainResponse,
    classifier_train_task,
    detector_train_task,
    segmenter_train_task,
    train_jobs_task,
    train_status_task,
)


class TestTrainRequests:
    def test_detector_request_inherits_common_defaults(self):
        request = DetectorTrainRequest(dataset_path="/tmp/dataset.yaml")

        assert request.epochs == 50
        assert request.batch_size == 16
        assert request.device == "auto"
        assert request.model_size == "n"
        assert request.img_size == 640
        assert request.params == {}

    def test_classifier_request_keeps_nested_configuration(self):
        request = ClassifierTrainRequest(
            dataset_path="/tmp/data",
            class_names=["ok", "bad"],
            backbone_config={"name": "resnet18", "pretrained": True},
            params={"workers": 4},
        )

        assert request.class_names == ["ok", "bad"]
        assert request.backbone_config["pretrained"] is True
        assert request.scheduler == "cosine"
        assert request.mixed_precision is True
        assert request.params == {"workers": 4}

    def test_segmenter_request_defaults_id2label_to_empty_dict(self):
        request = SegmenterTrainRequest(dataset_path="/tmp/segmenter")

        assert request.id2label == {}
        assert "mask2former" in request.hf_model_name

    def test_common_field_validation_rejects_non_positive_epochs(self):
        with pytest.raises(Exception):
            DetectorTrainRequest(dataset_path="/tmp/dataset.yaml", epochs=0)


class TestTrainResponses:
    def test_train_response_defaults(self):
        response = TrainResponse()

        assert response.status == "completed"
        assert response.metrics == {}
        assert response.best_checkpoint is None
        assert response.model_name == ""
        assert response.message == ""

    def test_job_models_capture_status_and_metrics(self):
        queued = TrainJobResponse(job_id="job-1", message="queued")
        status = TrainJobStatus(job_id="job-1", status="running", current_epoch=2, total_epochs=10)

        assert queued.status == "queued"
        assert status.epoch_metrics == []
        assert status.final_metrics == {}
        assert status.error is None
        assert status.best_checkpoint is None


class TestTrainingTaskSchemas:
    def test_train_task_registrations_use_expected_schemas(self):
        assert detector_train_task.name == "train"
        assert detector_train_task.input_schema is DetectorTrainRequest
        assert detector_train_task.output_schema is TrainResponse

        assert segmenter_train_task.input_schema is SegmenterTrainRequest
        assert classifier_train_task.input_schema is ClassifierTrainRequest

    def test_status_and_jobs_task_registrations(self):
        assert train_status_task.name == "train_status"
        assert train_status_task.input_schema is None
        assert train_status_task.output_schema is TrainJobStatus

        assert train_jobs_task.name == "train_jobs"
        assert train_jobs_task.input_schema is None
        assert train_jobs_task.output_schema is None
