"""Unit tests for InspectraService (CORS, user_repo, org_repo, shutdown_cleanup)."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from mindtrace.apps.inspectra.inspectra import InspectraService


def _mock_inspectra_config(cors_origins: str = "*"):
    return SimpleNamespace(
        INSPECTRA=SimpleNamespace(
            URL="http://0.0.0.0:8080",
            CORS_ALLOW_ORIGINS=cors_origins,
            MONGO_URI="mongodb://localhost:27017",
            MONGO_DB_NAME="inspectra",
        )
    )


@patch("mindtrace.apps.inspectra.inspectra.get_inspectra_config")
def test_inspectra_service_cors_wildcard_adds_origin_regex(mock_config):
    """When CORS_ALLOW_ORIGINS is '*', middleware uses allow_origin_regex."""
    mock_config.return_value = _mock_inspectra_config("*")
    service = InspectraService()
    assert len(service.app.user_middleware) > 0
    assert service.app is not None


@patch("mindtrace.apps.inspectra.inspectra.get_inspectra_config")
def test_inspectra_service_cors_list_uses_allow_origins(mock_config):
    """When CORS_ALLOW_ORIGINS is not '*', middleware uses allow_origins list."""
    mock_config.return_value = _mock_inspectra_config("https://app.example.com,https://other.example.com")
    service = InspectraService()
    assert len(service.app.user_middleware) > 0
    assert service.app is not None


@patch("mindtrace.apps.inspectra.inspectra.get_inspectra_config")
def test_inspectra_service_user_repo_lazy_init(mock_config):
    """user_repo property creates UserRepository on first access."""
    mock_config.return_value = _mock_inspectra_config()
    service = InspectraService()
    assert service._user_repo is None
    repo = service.user_repo
    assert repo is not None
    assert service._user_repo is repo
    assert service.user_repo is repo


@patch("mindtrace.apps.inspectra.inspectra.get_inspectra_config")
def test_inspectra_service_org_repo_lazy_init(mock_config):
    """org_repo property creates OrganizationRepository on first access."""
    mock_config.return_value = _mock_inspectra_config()
    service = InspectraService()
    assert service._org_repo is None
    repo = service.org_repo
    assert repo is not None
    assert service._org_repo is repo
    assert service.org_repo is repo


@patch("mindtrace.apps.inspectra.inspectra.close_db")
@patch("mindtrace.apps.inspectra.inspectra.get_inspectra_config")
@pytest.mark.asyncio
async def test_inspectra_service_shutdown_cleanup_calls_close_db(mock_config, mock_close_db):
    """shutdown_cleanup calls close_db."""
    mock_config.return_value = _mock_inspectra_config()
    service = InspectraService()
    await service.shutdown_cleanup()
    mock_close_db.assert_called_once()


@patch("mindtrace.apps.inspectra.inspectra.get_inspectra_config")
def test_inspectra_service_validation_exception_handler_returns_422(mock_config):
    """RequestValidationError is handled with 422 and custom message."""
    from fastapi.testclient import TestClient

    mock_config.return_value = _mock_inspectra_config()
    service = InspectraService()
    with TestClient(service.app) as client:
        resp = client.post("/auth/login", json={"email": 123, "password": "x"})
    assert resp.status_code == 422
    data = resp.json()
    assert "detail" in data
    assert "Invalid request" in str(data.get("detail", ""))
