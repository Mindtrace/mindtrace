from unittest.mock import MagicMock, patch

import pytest

from mindtrace.cluster.core import types as cluster_types
from mindtrace.cluster.core.cluster import ClusterManager
from mindtrace.jobs import Job
from mindtrace.jobs.types.job_specs import ExecutionStatus


@pytest.fixture
def cluster_manager():
    # Patch Registry to avoid file I/O
    with patch("mindtrace.cluster.core.cluster.Registry") as MockRegistry:
        mock_registry = MockRegistry.return_value
        mock_registry.save = MagicMock()
        mock_registry.load = MagicMock(return_value={})
        cm = ClusterManager()
        cm._registry = mock_registry
        # Patch _url using object.__setattr__ to bypass type checks
        object.__setattr__(cm, "_url", "http://localhost")
        return cm


def make_job(schema_name="test_job", payload=None):
    return Job(
        id="jobid",
        name="Test Job",
        schema_name=schema_name,
        payload=payload or {"foo": "bar"},
        status=ExecutionStatus.QUEUED,
        created_at="2024-01-01T00:00:00",
    )


def test_register_job_to_endpoint(cluster_manager):
    payload = cluster_types.RegisterJobToEndpointInput(job_type="test_job", endpoint="/test")
    cluster_manager.register_job_to_endpoint(payload)
    assert cluster_manager._job_registry["test_job"] == "/test"
    cluster_manager._registry.save.assert_called_with("jobregistry", cluster_manager._job_registry)


def test_submit_job_success(cluster_manager):
    job = make_job(schema_name="test_job")
    cluster_manager._job_registry["test_job"] = "/test"
    with patch("mindtrace.cluster.core.cluster.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"status": "success", "output": {"result": 42}}
        result = cluster_manager.submit_job(job)
        assert result.status == "success"
        assert result.output == {"result": 42}
        mock_post.assert_called_once()


def test_submit_job_registry_reload(cluster_manager):
    job = make_job(schema_name="test_job")
    # _job_registry does not have the job, but registry.load does
    cluster_manager._job_registry = {}
    cluster_manager._registry.load.return_value = {"test_job": "/test"}
    with patch("mindtrace.cluster.core.cluster.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"status": "success", "output": {"result": 42}}
        result = cluster_manager.submit_job(job)
        assert result.status == "success"
        assert result.output == {"result": 42}
        mock_post.assert_called_once()


def test_submit_job_failure(cluster_manager):
    job = make_job(schema_name="unknown_job")
    cluster_manager._job_registry = {}
    cluster_manager._registry.load.return_value = {}
    result = cluster_manager.submit_job(job)
    assert result.status == "failed"
    assert result.output == {}


def test__submit_job_to_endpoint_http_error(cluster_manager):
    job = make_job(schema_name="test_job")
    cluster_manager._job_registry["test_job"] = "/test"
    with patch("mindtrace.cluster.core.cluster.requests.post") as mock_post:
        mock_post.return_value.status_code = 500
        mock_post.return_value.text = "Internal Server Error"
        with pytest.raises(RuntimeError):
            cluster_manager._submit_job_to_endpoint(job)


def test__submit_job_to_endpoint_json_error(cluster_manager):
    job = make_job(schema_name="test_job")
    cluster_manager._job_registry["test_job"] = "/test"
    with patch("mindtrace.cluster.core.cluster.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.side_effect = Exception("bad json")
        result = cluster_manager._submit_job_to_endpoint(job)
        assert result.status == "success"
        assert result.output == {}  # fallback on JSON error
