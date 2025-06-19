import os
import logging
import tempfile
import shutil
from pathlib import Path
import pytest
from mindtrace.core.logging.logger import setup_logger, get_logger

class TestLogger:
    """Unit tests for logger setup and retrieval in mindtrace.core.logging.logger."""

    def test_setup_logger_creates_log_file_and_handlers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            logger = setup_logger(
                name="test_logger",
                log_dir=log_dir,
                logger_level=logging.INFO,
                stream_level=logging.WARNING,
                file_level=logging.INFO,
                file_mode="w",
                propagate=False,
                max_bytes=1024,
                backup_count=1
            )
            # Check logger name
            assert logger.name == "test_logger"
            # Check handlers
            handler_types = {type(h) for h in logger.handlers}
            assert logging.StreamHandler in handler_types
            assert any("RotatingFileHandler" in str(type(h)) for h in logger.handlers)
            # Check log file creation
            log_file = log_dir / "misc" / "test_logger.log"
            assert log_file.exists()
            # Write a log and check file content
            logger.info("Test log message")
            with open(log_file) as f:
                content = f.read()
            assert "Test log message" in content

    def test_get_logger_returns_configured_logger(self, tmp_path):
        logger = get_logger(
            name="unit.test_get_logger",
            log_dir=tmp_path,
            logger_level=logging.DEBUG,
            stream_level=logging.ERROR,
            file_level=logging.DEBUG,
            file_mode="w",
            propagate=True,
            max_bytes=1024,
            backup_count=1
        )
        assert logger.name == "mindtrace.unit.test_get_logger"
        # Should have both StreamHandler and RotatingFileHandler
        handler_types = {type(h) for h in logger.handlers}
        assert logging.StreamHandler in handler_types
        assert any("RotatingFileHandler" in str(type(h)) for h in logger.handlers)
        # Log file should exist
        log_file = tmp_path / "misc" / "mindtrace.unit.test_get_logger.log"
        assert log_file.exists()
        logger.debug("Debug message")
        with open(log_file) as f:
            content = f.read()
        assert "Debug message" in content 