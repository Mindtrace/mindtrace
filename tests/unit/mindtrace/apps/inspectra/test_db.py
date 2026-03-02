"""Unit tests for Inspectra db module (init_db, close_db)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mindtrace.apps.inspectra import db


@pytest.mark.asyncio
async def test_init_db_calls_odm_initialize():
    """init_db calls get_odm().initialize()."""
    mock_odm = MagicMock()
    mock_odm.initialize = AsyncMock()
    with patch.object(db, "get_odm", return_value=mock_odm):
        await db.init_db()
    mock_odm.initialize.assert_called_once()


def test_close_db_closes_client_when_odm_set():
    """close_db closes client and clears _odm when _odm has client."""
    mock_client = MagicMock()
    mock_odm = MagicMock()
    mock_odm.client = mock_client
    with patch.object(db, "_odm", mock_odm):
        db.close_db()
    mock_client.close.assert_called_once()
    assert db._odm is None


@patch("mindtrace.apps.inspectra.db.MongoMindtraceODM")
@patch("mindtrace.apps.inspectra.db.get_inspectra_config")
def test_get_odm_creates_odm_when_none(mock_config, mock_odm_class):
    """get_odm creates and caches MongoMindtraceODM when _odm is None."""
    mock_config.return_value.INSPECTRA.MONGO_URI = "mongodb://localhost:27017"
    mock_config.return_value.INSPECTRA.MONGO_DB_NAME = "test"
    mock_instance = MagicMock()
    mock_odm_class.return_value = mock_instance
    with patch.object(db, "_odm", None):
        result = db.get_odm()
    assert result is mock_instance
    mock_odm_class.assert_called_once()
