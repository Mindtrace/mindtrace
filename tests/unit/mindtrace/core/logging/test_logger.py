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
            log_file = log_dir / "modules" / "test_logger.log"
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
        log_file = tmp_path / "modules" / "mindtrace.unit.test_get_logger.log"
        assert log_file.exists()
        logger.debug("Debug message")
        with open(log_file) as f:
            content = f.read()
        assert "Debug message" in content


class TestGetLoggerNameValidation:
    """Tests for the name validation and default assignment functionality in get_logger."""

    def test_get_logger_with_none_name_uses_default(self, tmp_path):
        """Test that passing None as name results in default 'mindtrace' name."""
        logger = get_logger(name=None, log_dir=tmp_path)
        
        # Should use the default "mindtrace" name
        assert logger.name == "mindtrace"
        
        # Verify the logger is functional
        logger.info("Test message with None name")
        log_file = tmp_path / "mindtrace.log"
        assert log_file.exists()

    def test_get_logger_with_empty_string_name_uses_default(self, tmp_path):
        """Test that passing empty string as name results in default 'mindtrace' name."""
        logger = get_logger(name="", log_dir=tmp_path)
        
        # Should use the default "mindtrace" name
        assert logger.name == "mindtrace"
        
        # Verify the logger is functional
        logger.info("Test message with empty string name")
        log_file = tmp_path / "mindtrace.log"
        assert log_file.exists()

    def test_get_logger_with_whitespace_only_name_uses_default(self, tmp_path):
        """Test that passing whitespace-only string as name results in default 'mindtrace' name."""
        test_cases = ["   ", "\t", "\n", "\r", " \t\n\r "]
        
        for whitespace_name in test_cases:
            logger = get_logger(name=whitespace_name, log_dir=tmp_path)
            
            # Whitespace strings are truthy in Python, so they should NOT trigger the default
            # This tests the boundary condition - only truly falsy values trigger the default
            expected_name = f"mindtrace.{whitespace_name}"
            assert logger.name == expected_name

    def test_get_logger_with_falsy_values_uses_default(self, tmp_path):
        """Test that various falsy values result in default 'mindtrace' name."""
        falsy_values = [None, "", 0, False, [], {}]
        
        for falsy_value in falsy_values:
            logger = get_logger(name=falsy_value, log_dir=tmp_path)
            
            # All falsy values should trigger the default assignment
            assert logger.name == "mindtrace"
            
            # Verify the logger is functional
            logger.info(f"Test message with falsy value: {falsy_value}")
            log_file = tmp_path / "mindtrace.log"
            assert log_file.exists()

    def test_get_logger_with_valid_name_preserves_name(self, tmp_path):
        """Test that valid (truthy) names are preserved and not replaced with default."""
        valid_names = [
            "custom_logger",
            "module.submodule", 
            "1",  # String "1" is truthy
            "test",
            "a",  # Single character
            "mindtrace.custom"  # Already prefixed
        ]
        
        for valid_name in valid_names:
            logger = get_logger(name=valid_name, log_dir=tmp_path)
            
            # Valid names should be preserved (with mindtrace prefix if not already present)
            if valid_name.startswith("mindtrace"):
                expected_name = valid_name
            else:
                expected_name = f"mindtrace.{valid_name}"
            
            assert logger.name == expected_name

    def test_get_logger_default_assignment_with_subsequent_processing(self, tmp_path):
        """Test that after default assignment, the name goes through normal processing."""
        logger = get_logger(name=None, log_dir=tmp_path)
        
        # After default assignment (name = "mindtrace"), it should go through the normal flow
        # Since "mindtrace" already starts with "mindtrace", it shouldn't get prefixed again
        assert logger.name == "mindtrace"
        
        # Verify the logger has proper handlers and configuration
        handler_types = {type(h) for h in logger.handlers}
        assert logging.StreamHandler in handler_types
        assert any("RotatingFileHandler" in str(type(h)) for h in logger.handlers)

    def test_get_logger_default_assignment_execution_flow(self, tmp_path):
        """Test the execution flow when default assignment occurs."""
        # This test specifically targets the code path where default assignment happens
        
        from unittest.mock import patch
        
        with patch('mindtrace.core.logging.logger.setup_logger') as mock_setup:
            # Configure the mock to return a simple logger
            mock_logger = logging.getLogger("test_mock")
            mock_setup.return_value = mock_logger
            
            # Call with None name - should trigger default assignment
            result_logger = get_logger(name=None, log_dir=tmp_path)
            
            # Verify setup_logger was called with the default name "mindtrace"
            mock_setup.assert_called_once()
            call_args = mock_setup.call_args
            assert call_args[0][0] == "mindtrace"  # First positional argument should be "mindtrace"
            
            # Verify the returned logger is what we expected
            assert result_logger is mock_logger

    def test_get_logger_boundary_conditions_for_name_validation(self, tmp_path):
        """Test boundary conditions around the name validation logic."""
        # Test the exact boundary between falsy and truthy values
        
        # These should trigger default assignment (falsy)
        falsy_cases = [None, "", False, 0, 0.0]
        
        for falsy_case in falsy_cases:
            logger = get_logger(name=falsy_case, log_dir=tmp_path)
            assert logger.name == "mindtrace"
        
        # These should NOT trigger default assignment (truthy)
        # Note: Only testing string values since the function expects strings
        truthy_cases = ["0", "False", " ", "a", "test"]
        
        for truthy_case in truthy_cases:
            logger = get_logger(name=truthy_case, log_dir=tmp_path)
            expected_name = truthy_case if truthy_case.startswith("mindtrace") else f"mindtrace.{truthy_case}"
            assert logger.name == expected_name

    def test_get_logger_with_non_string_falsy_values(self, tmp_path):
        """Test that non-string falsy values are handled correctly."""
        # These are falsy values that aren't strings but should still trigger default assignment
        non_string_falsy_values = [[], {}, set(), 0, False]
        
        for falsy_value in non_string_falsy_values:
            logger = get_logger(name=falsy_value, log_dir=tmp_path)
            # Should use default name since these are falsy
            assert logger.name == "mindtrace"

    def test_get_logger_default_assignment_with_kwargs(self, tmp_path):
        """Test that kwargs are properly passed through when default assignment occurs."""
        logger = get_logger(
            name=None,  # Should trigger default assignment
            log_dir=tmp_path,
            logger_level=logging.WARNING,
            stream_level=logging.CRITICAL,
            file_level=logging.INFO,
            propagate=False
        )
        
        # Should use default name
        assert logger.name == "mindtrace"
        
        # Should respect the kwargs that were passed
        assert logger.level == logging.WARNING
        assert logger.propagate == False  # Should override the default True
        
        # Verify handlers have correct levels
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler) and not hasattr(handler, 'baseFilename'):
                assert handler.level == logging.CRITICAL
            elif hasattr(handler, 'baseFilename'):  # File handler
                assert handler.level == logging.INFO 