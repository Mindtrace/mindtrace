"""Unit checks of fixture error classification; no network or integration execution."""

from unittest.mock import Mock

import pytest
from botocore.exceptions import EndpointConnectionError

from tests.integration import conftest as shared
from tests.integration.mindtrace.registry.core import conftest as hunt
from tests.integration.mindtrace.registry.core import test_all_supported_backends as all_backends
from tests.integration.mindtrace.registry.core import test_registry_cache as cache_tests

S3_CONFIG = {"endpoint": "example.invalid", "access_key": "test", "secret_key": "test", "secure": False}


def test_unexpected_s3_client_error_is_not_skipped(monkeypatch):
    client = Mock()
    client.list_buckets.side_effect = ValueError("unexpected client failure")
    monkeypatch.setattr(shared, "make_s3_client", Mock(return_value=client))
    with pytest.raises(ValueError, match="unexpected client failure"):
        next(shared.s3_client.__wrapped__(S3_CONFIG))
    client.list_buckets.assert_called_once()


def test_missing_s3_service_is_an_explicit_prerequisite_skip(monkeypatch):
    client = Mock()
    client.list_buckets.side_effect = EndpointConnectionError(endpoint_url="http://example.invalid")
    monkeypatch.setattr(shared, "make_s3_client", Mock(return_value=client))
    with pytest.raises(pytest.skip.Exception, match="S3 test service unavailable"):
        next(shared.s3_client.__wrapped__(S3_CONFIG))


def test_unexpected_s3_backend_error_is_not_skipped(monkeypatch, tmp_path):
    constructor = Mock(side_effect=RuntimeError("backend implementation error"))
    monkeypatch.setattr(shared, "S3RegistryBackend", constructor)
    with pytest.raises(RuntimeError, match="backend implementation error"):
        next(shared.s3_backend.__wrapped__(tmp_path, "bucket", S3_CONFIG))
    constructor.assert_called_once()


@pytest.mark.parametrize("fixture", ["hunt", "cache", "all_backends"])
def test_unexpected_gcp_backend_error_is_not_skipped(monkeypatch, fixture):
    constructor = Mock(side_effect=RuntimeError("backend implementation error"))
    if fixture == "hunt":
        monkeypatch.setattr("mindtrace.registry.backends.gcp_registry_backend.GCPRegistryBackend", constructor)
        operation = hunt.gcp_object_backend.__wrapped__
    elif fixture == "cache":
        monkeypatch.setattr(cache_tests, "GCPRegistryBackend", constructor)
        operation = cache_tests.gcp_backend.__wrapped__
    else:
        monkeypatch.setattr(all_backends, "GCPRegistryBackend", constructor)
        operation = all_backends.gcp_backend_instance.__wrapped__
    with pytest.raises(RuntimeError, match="backend implementation error"):
        if fixture == "cache":
            operation("bucket", "prefix", "project", None)
        else:
            next(operation("bucket", "prefix", "project", None, Mock()))
    constructor.assert_called_once()


def test_unexpected_gcp_bucket_error_is_not_skipped():
    client = Mock()
    client.bucket.return_value.exists.side_effect = ValueError("bad bucket response")
    with pytest.raises(ValueError, match="bad bucket response"):
        next(shared.gcp_test_bucket.__wrapped__(client, "bucket"))
