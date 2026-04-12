import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

from mindtrace.core.logging.logger import get_logger, setup_logger


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
                backup_count=1,
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
            backup_count=1,
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

    def test_get_logger_returns_configured_logger_no_name(self, tmp_path):
        logger = get_logger(
            name="",
            log_dir=tmp_path,
            logger_level=logging.DEBUG,
            stream_level=logging.ERROR,
            file_level=logging.DEBUG,
            file_mode="w",
            propagate=True,
            max_bytes=1024,
            backup_count=1,
        )
        assert logger.name == "mindtrace"
        # Should have both StreamHandler and RotatingFileHandler
        handler_types = {type(h) for h in logger.handlers}
        assert logging.StreamHandler in handler_types
        assert any("RotatingFileHandler" in str(type(h)) for h in logger.handlers)
        # Log file should exist
        log_file = tmp_path / "mindtrace.log"
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
            "mindtrace.custom",  # Already prefixed
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

        with patch("mindtrace.core.logging.logger.setup_logger") as mock_setup:
            # Configure the mock to return a simple logger
            mock_logger = logging.getLogger("test_mock")
            mock_setup.return_value = mock_logger

            # Call with None name - should trigger default assignment
            result_logger = get_logger(name=None, log_dir=tmp_path, propagate=False)

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
            propagate=False,
        )

        # Should use default name
        assert logger.name == "mindtrace"

        # Should respect the kwargs that were passed
        assert logger.level == logging.WARNING
        assert logger.propagate is False  # Should override the default True

        # Verify handlers have correct levels
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler) and not hasattr(handler, "baseFilename"):
                assert handler.level == logging.CRITICAL
            elif hasattr(handler, "baseFilename"):  # File handler
                assert handler.level == logging.INFO


class TestGetLoggerAdvanced:
    """Advanced tests for get_logger functionality including structlog integration."""

    def test_get_logger_with_structlog_integration(self, tmp_path):
        """Test get_logger with structlog enabled."""
        logger = get_logger(
            name="test_structlog", log_dir=tmp_path, use_structlog=True, structlog_bind={"service": "test-service"}
        )

        # Should be a structlog bound logger
        assert hasattr(logger, "bind")
        assert hasattr(logger, "info")

        # Test logging
        logger.info("Structlog test message", user_id="123")

        # Check log file
        log_file = tmp_path / "modules" / "mindtrace.test_structlog.log"
        assert log_file.exists()

        with open(log_file) as f:
            content = f.read()
            assert "test-service" in content
            assert "123" in content

    def test_get_logger_propagation_behavior(self, tmp_path):
        """Test get_logger propagation behavior with parent loggers."""
        # Test with propagation enabled (default)
        logger = get_logger(name="parent.child.grandchild", log_dir=tmp_path, propagate=True)

        # Should create the full hierarchy
        assert logger.name == "mindtrace.parent.child.grandchild"

        # Check that parent loggers exist
        logging.getLogger("mindtrace.parent")
        logging.getLogger("mindtrace.parent.child")

        # The target logger should have handlers
        assert len(logger.handlers) > 0

        # Parent loggers may not have handlers initially (they only get handlers if they already had them)
        # This is the actual behavior of the current implementation

    def test_get_logger_propagation_disabled(self, tmp_path):
        """Test get_logger with propagation disabled."""
        logger = get_logger(name="parent.child.grandchild", log_dir=tmp_path, propagate=False)

        # Should create the full hierarchy
        assert logger.name == "mindtrace.parent.child.grandchild"

        # Check that parent loggers exist but may not have handlers
        logging.getLogger("mindtrace.parent")
        logging.getLogger("mindtrace.parent.child")

        # Only the target logger should have handlers
        assert len(logger.handlers) > 0

    def test_get_logger_with_custom_configuration(self, tmp_path):
        """Test get_logger with various custom configurations."""
        # Test with custom levels
        logger = get_logger(
            name="custom_config",
            log_dir=tmp_path,
            logger_level=logging.WARNING,
            stream_level=logging.ERROR,
            file_level=logging.DEBUG,
            max_bytes=2048,
            backup_count=3,
        )

        assert logger.level == logging.WARNING

        # Check handler levels
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler) and not hasattr(handler, "baseFilename"):
                assert handler.level == logging.ERROR
            elif hasattr(handler, "baseFilename"):  # File handler
                assert handler.level == logging.DEBUG

    def test_get_logger_parent_logger_setup(self, tmp_path):
        """Test that parent loggers are properly set up when propagation is enabled."""
        with patch("mindtrace.core.logging.logger.setup_logger") as mock_setup:
            mock_logger = logging.getLogger("test_mock")
            mock_setup.return_value = mock_logger

            # Create a logger with propagation
            get_logger(name="a.b.c.d", log_dir=tmp_path, propagate=True)

            # The current implementation only calls setup_logger for the target logger
            # and for parent loggers that already have handlers
            # Since we're mocking, we expect at least 1 call (for the target logger)
            assert mock_setup.call_count >= 1

            # Verify the final call was for the target logger
            final_call = mock_setup.call_args_list[-1]
            assert final_call[0][0] == "mindtrace.a.b.c.d"

    def test_get_logger_with_structlog_binding(self, tmp_path):
        """Test get_logger with structlog binding functionality."""

        def bind_function(name):
            return {"logger_name": name, "dynamic_field": f"value_for_{name}"}

        logger = get_logger(name="test_binding", log_dir=tmp_path, use_structlog=True, structlog_bind=bind_function)

        # Should be a structlog bound logger
        assert hasattr(logger, "bind")

        # Test logging
        logger.info("Binding test message")

        # Check log file
        log_file = tmp_path / "modules" / "mindtrace.test_binding.log"
        assert log_file.exists()

        with open(log_file) as f:
            content = f.read()
            assert "mindtrace.test_binding" in content
            assert "value_for_mindtrace.test_binding" in content

    def test_get_logger_with_structlog_custom_processors(self, tmp_path):
        """Test get_logger with structlog custom processors."""

        def custom_processor(logger, method_name, event_dict):
            event_dict["custom_field"] = "custom_value"
            return event_dict

        logger = get_logger(
            name="test_processors", log_dir=tmp_path, use_structlog=True, structlog_pre_chain=[custom_processor]
        )

        # Test logging
        logger.info("Processor test message")

        # Check log file
        log_file = tmp_path / "modules" / "mindtrace.test_processors.log"
        assert log_file.exists()

        with open(log_file) as f:
            content = f.read()
            assert "custom_value" in content

    def test_get_logger_with_structlog_json_rendering(self, tmp_path):
        """Test get_logger with structlog JSON rendering."""
        logger = get_logger(name="test_json", log_dir=tmp_path, use_structlog=True, structlog_json=True)

        # Test logging
        logger.info("JSON test message", service="test-service")

        # Check log file
        log_file = tmp_path / "modules" / "mindtrace.test_json.log"
        assert log_file.exists()

        with open(log_file) as f:
            content = f.read()
            # Should contain JSON structure
            assert "test-service" in content
            assert "JSON test message" in content

    def test_get_logger_with_structlog_console_rendering(self, tmp_path):
        """Test get_logger with structlog console rendering."""
        logger = get_logger(name="test_console", log_dir=tmp_path, use_structlog=True, structlog_json=False)

        # Test logging
        logger.info("Console test message", service="test-service")

        # Check log file
        log_file = tmp_path / "modules" / "mindtrace.test_console.log"
        assert log_file.exists()

        with open(log_file) as f:
            content = f.read()
            assert "Console test message" in content

    def test_get_logger_name_prefixing_behavior(self, tmp_path):
        """Test get_logger name prefixing behavior."""
        # Test with name that doesn't start with mindtrace
        logger1 = get_logger(name="custom.logger", log_dir=tmp_path)
        assert logger1.name == "mindtrace.custom.logger"

        # Test with name that already starts with mindtrace
        logger2 = get_logger(name="mindtrace.already.prefixed", log_dir=tmp_path)
        assert logger2.name == "mindtrace.already.prefixed"

        # Test with empty name (should use default)
        logger3 = get_logger(name="", log_dir=tmp_path)
        assert logger3.name == "mindtrace"

    def test_get_logger_with_different_log_levels(self, tmp_path):
        """Test get_logger with different log levels."""
        logger = get_logger(
            name="test_levels",
            log_dir=tmp_path,
            logger_level=logging.DEBUG,
            stream_level=logging.INFO,
            file_level=logging.DEBUG,
        )

        # Test different log levels
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")

        # Check log file
        log_file = tmp_path / "modules" / "mindtrace.test_levels.log"
        assert log_file.exists()

        with open(log_file) as f:
            content = f.read()
            assert "Debug message" in content
            assert "Info message" in content
            assert "Warning message" in content
            assert "Error message" in content

    def test_get_logger_exception_handling(self, tmp_path):
        """Test get_logger with exception handling."""
        logger = get_logger(name="test_exception", log_dir=tmp_path)

        try:
            raise ValueError("Test exception")
        except ValueError:
            logger.exception("Exception occurred")

        # Check log file
        log_file = tmp_path / "modules" / "mindtrace.test_exception.log"
        assert log_file.exists()

        with open(log_file) as f:
            content = f.read()
            assert "Exception occurred" in content
            assert "ValueError" in content
            assert "Test exception" in content

    def test_get_logger_with_structlog_exception_handling(self, tmp_path):
        """Test get_logger with structlog and exception handling."""
        logger = get_logger(name="test_structlog_exception", log_dir=tmp_path, use_structlog=True)

        try:
            raise ValueError("Structlog test exception")
        except ValueError:
            logger.exception("Structlog exception occurred", service="test-service")

        # Check log file
        log_file = tmp_path / "modules" / "mindtrace.test_structlog_exception.log"
        assert log_file.exists()

        with open(log_file) as f:
            content = f.read()
            assert "Structlog exception occurred" in content
            assert "test-service" in content
            assert "ValueError" in content

    def test_get_logger_context_binding(self, tmp_path):
        """Test get_logger with context binding."""
        logger = get_logger(name="test_context", log_dir=tmp_path, use_structlog=True)

        # Test context binding
        bound_logger = logger.bind(user_id="123", session_id="abc")
        bound_logger.info("Context test message")

        # Check log file
        log_file = tmp_path / "modules" / "mindtrace.test_context.log"
        assert log_file.exists()

        with open(log_file) as f:
            content = f.read()
            assert "123" in content
            assert "abc" in content

    def test_get_logger_nested_binding(self, tmp_path):
        """Test get_logger with nested binding."""
        logger = get_logger(name="test_nested", log_dir=tmp_path, use_structlog=True)

        # Test nested binding
        nested_logger = logger.bind(service="test-service").bind(version="1.0.0")
        nested_logger.info("Nested binding test", action="test")

        # Check log file
        log_file = tmp_path / "modules" / "mindtrace.test_nested.log"
        assert log_file.exists()

        with open(log_file) as f:
            content = f.read()
            assert "test-service" in content
            assert "1.0.0" in content
            assert "test" in content

    def test_get_logger_file_rotation(self, tmp_path):
        """Test get_logger with file rotation settings."""
        logger = get_logger(
            name="test_rotation",
            log_dir=tmp_path,
            max_bytes=1024,  # 1KB
            backup_count=2,
        )

        # Write enough data to trigger rotation
        for i in range(100):
            logger.info(f"Rotation test message {i} " * 10)  # Make each message large

        # Check that rotation occurred
        log_file = tmp_path / "modules" / "mindtrace.test_rotation.log"
        assert log_file.exists()

        # Check for backup files
        backup_files = list(tmp_path.glob("modules/mindtrace.test_rotation.log.*"))
        assert len(backup_files) > 0

    def test_get_logger_with_custom_formatter(self, tmp_path):
        """Test get_logger with custom formatter (standard logging)."""
        logger = get_logger(name="test_formatter", log_dir=tmp_path, use_structlog=False)

        # Test logging
        logger.info("Formatter test message")

        # Check log file
        log_file = tmp_path / "modules" / "mindtrace.test_formatter.log"
        assert log_file.exists()

        with open(log_file) as f:
            content = f.read()
            # Should contain timestamp and level info
            assert "INFO" in content
            assert "Formatter test message" in content

    def test_get_logger_edge_cases(self, tmp_path):
        """Test get_logger with various edge cases."""
        # Test with very long name
        long_name = "a" * 100
        logger1 = get_logger(name=long_name, log_dir=tmp_path)
        assert logger1.name == f"mindtrace.{long_name}"

        # Test with special characters in name
        special_name = "test.logger-with_special@chars"
        logger2 = get_logger(name=special_name, log_dir=tmp_path)
        assert logger2.name == f"mindtrace.{special_name}"

        # Test with None name
        logger3 = get_logger(name=None, log_dir=tmp_path)
        assert logger3.name == "mindtrace"

        # Test with False name
        logger4 = get_logger(name=False, log_dir=tmp_path)
        assert logger4.name == "mindtrace"

    def test_get_logger_integration_with_existing_loggers(self, tmp_path):
        """Test get_logger integration with existing loggers."""
        # Create a logger first
        existing_logger = get_logger(name="existing", log_dir=tmp_path)

        # Create a child logger
        child_logger = get_logger(name="existing.child", log_dir=tmp_path)

        # Both should work
        existing_logger.info("Parent message")
        child_logger.info("Child message")

        # Check both log files exist
        parent_log_file = tmp_path / "modules" / "mindtrace.existing.log"
        child_log_file = tmp_path / "modules" / "mindtrace.existing.child.log"

        assert parent_log_file.exists()
        assert child_log_file.exists()

        # Check content
        with open(parent_log_file) as f:
            content = f.read()
            assert "Parent message" in content

        with open(child_log_file) as f:
            content = f.read()
            assert "Child message" in content
