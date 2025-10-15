import json
import logging
from pathlib import Path
from unittest.mock import Mock, call, patch

import pytest

from mindtrace.services.core.launcher import Launcher, main


class TestLauncher:
    """Test suite for the Launcher class."""

    @pytest.fixture
    def mock_options(self):
        """Create mock options object for testing."""
        options = Mock()
        options.bind = "127.0.0.1:8080"
        options.num_workers = 2
        options.worker_class = "uvicorn.workers.UvicornWorker"
        options.pid = "/tmp/test.pid"
        options.server_class = "test.server.TestServer"
        options.init_params = '{"param1": "value1", "param2": 42}'
        return options

    @pytest.fixture
    def mock_server(self):
        """Create mock server object."""
        server = Mock()
        server.unique_name = "test_server"
        server.config = {"MINDTRACE_DIR_PATHS": {"LOGGER_DIR": "/tmp/logs"}}
        server.app = Mock()  # Mock WSGI/ASGI app
        return server

    @patch("mindtrace.services.core.launcher.instantiate_target")
    @patch("mindtrace.services.core.launcher.BaseApplication.__init__")
    def test_launcher_init_with_init_params(
        self, mock_base_init, mock_instantiate, mock_options, mock_server
    ):
        """Test Launcher initialization with init parameters."""
        # Setup mocks
        mock_instantiate.return_value = mock_server

        # Create launcher
        launcher = Launcher(mock_options)

        # Verify gunicorn options are set correctly
        expected_options = {
            "bind": "127.0.0.1:8080",
            "workers": 2,
            "worker_class": "uvicorn.workers.UvicornWorker",
            "pidfile": "/tmp/test.pid",
        }
        assert launcher.gunicorn_options == expected_options

        # Verify server instantiation
        mock_instantiate.assert_called_once_with("test.server.TestServer", param1="value1", param2=42)

        # Verify server configuration
        assert mock_server.url == "127.0.0.1:8080"
        assert launcher.application == mock_server.app

        # Verify BaseApplication initialization
        mock_base_init.assert_called_once()

    @patch("mindtrace.services.core.launcher.instantiate_target")
    @patch("mindtrace.services.core.launcher.BaseApplication.__init__")
    def test_launcher_init_without_init_params(self, mock_base_init, mock_instantiate, mock_server):
        """Test Launcher initialization without init parameters."""
        # Setup options without init_params
        options = Mock()
        options.bind = "0.0.0.0:9000"
        options.num_workers = 1
        options.worker_class = "sync"
        options.pid = None
        options.server_class = "default.Server"
        options.init_params = None

        mock_instantiate.return_value = mock_server

        # Create launcher
        launcher = Launcher(options)

        # Verify server instantiation with no init params
        mock_instantiate.assert_called_once_with("default.Server")

        # Verify gunicorn options
        expected_options = {
            "bind": "0.0.0.0:9000",
            "workers": 1,
            "worker_class": "sync",
            "pidfile": None,
        }
        assert launcher.gunicorn_options == expected_options

    @patch("mindtrace.services.core.launcher.instantiate_target")
    @patch("mindtrace.services.core.launcher.BaseApplication.__init__")
    def test_launcher_init_empty_init_params(self, mock_base_init, mock_instantiate, mock_server):
        """Test Launcher initialization with empty init parameters string."""
        options = Mock()
        options.bind = "127.0.0.1:8080"
        options.num_workers = 1
        options.worker_class = "uvicorn.workers.UvicornWorker"
        options.pid = None
        options.server_class = "test.Server"
        options.init_params = ""

        mock_instantiate.return_value = mock_server

        # Create launcher
        _ = Launcher(options)

        # Verify server instantiation with empty init params
        mock_instantiate.assert_called_once_with("test.Server")

    @patch("mindtrace.services.core.launcher.setup_logger")
    @patch("mindtrace.services.core.launcher.instantiate_target")
    @patch("mindtrace.services.core.launcher.BaseApplication.__init__")
    def test_launcher_init_invalid_json(self, mock_base_init, mock_instantiate, mock_setup_logger):
        """Test Launcher initialization with invalid JSON init parameters."""
        options = Mock()
        options.bind = "127.0.0.1:8080"
        options.num_workers = 1
        options.worker_class = "uvicorn.workers.UvicornWorker"
        options.pid = None
        options.server_class = "test.Server"
        options.init_params = "invalid json"

        # Should raise JSONDecodeError
        with pytest.raises(json.JSONDecodeError):
            Launcher(options)

    def test_load_config(self, mock_options, mock_server):
        """Test load_config method."""
        with (
            patch("mindtrace.services.core.launcher.setup_logger"),
            patch("mindtrace.services.core.launcher.instantiate_target", return_value=mock_server),
            patch("mindtrace.services.core.launcher.BaseApplication.__init__"),
        ):
            launcher = Launcher(mock_options)

            # Mock the cfg object
            launcher.cfg = Mock()
            launcher.cfg.settings = {
                "bind": Mock(),
                "workers": Mock(),
                "worker_class": Mock(),
                "pidfile": Mock(),
                "other_setting": Mock(),
            }

            # Call load_config
            launcher.load_config()

            # Verify cfg.set calls for valid settings
            expected_calls = [
                call("bind", "127.0.0.1:8080"),
                call("workers", 2),
                call("worker_class", "uvicorn.workers.UvicornWorker"),
                call("pidfile", "/tmp/test.pid"),
            ]
            launcher.cfg.set.assert_has_calls(expected_calls, any_order=True)
            assert launcher.cfg.set.call_count == 4

    def test_load_config_filters_none_values(self, mock_server):
        """Test load_config filters out None values."""
        options = Mock()
        options.bind = "127.0.0.1:8080"
        options.num_workers = 1
        options.worker_class = "sync"
        options.pid = None  # This should be filtered out
        options.server_class = "test.Server"
        options.init_params = None

        with (
            patch("mindtrace.services.core.launcher.setup_logger"),
            patch("mindtrace.services.core.launcher.instantiate_target", return_value=mock_server),
            patch("mindtrace.services.core.launcher.BaseApplication.__init__"),
        ):
            launcher = Launcher(options)
            launcher.cfg = Mock()
            launcher.cfg.settings = {
                "bind": Mock(),
                "workers": Mock(),
                "worker_class": Mock(),
                "pidfile": Mock(),
            }

            launcher.load_config()

            # Verify pidfile is not set since it's None
            expected_calls = [call("bind", "127.0.0.1:8080"), call("workers", 1), call("worker_class", "sync")]
            launcher.cfg.set.assert_has_calls(expected_calls, any_order=True)
            assert launcher.cfg.set.call_count == 3

    def test_load_config_filters_unsupported_settings(self, mock_options, mock_server):
        """Test load_config only sets supported settings."""
        with (
            patch("mindtrace.services.core.launcher.setup_logger"),
            patch("mindtrace.services.core.launcher.instantiate_target", return_value=mock_server),
            patch("mindtrace.services.core.launcher.BaseApplication.__init__"),
        ):
            launcher = Launcher(mock_options)
            launcher.cfg = Mock()
            # Only some settings are supported
            launcher.cfg.settings = {
                "bind": Mock(),
                "workers": Mock(),
                # worker_class and pidfile not in settings
            }

            launcher.load_config()

            # Only supported settings should be set
            expected_calls = [
                call("bind", "127.0.0.1:8080"),
                call("workers", 2),
            ]
            launcher.cfg.set.assert_has_calls(expected_calls, any_order=True)
            assert launcher.cfg.set.call_count == 2

    def test_load(self, mock_options, mock_server):
        """Test load method returns the application."""
        with (
            patch("mindtrace.services.core.launcher.setup_logger"),
            patch("mindtrace.services.core.launcher.instantiate_target", return_value=mock_server),
            patch("mindtrace.services.core.launcher.BaseApplication.__init__"),
        ):
            launcher = Launcher(mock_options)
            result = launcher.load()

            assert result == mock_server.app
            assert result == launcher.application


class TestMain:
    """Test suite for the main function."""

    @patch("mindtrace.services.core.launcher.Launcher")
    @patch("argparse.ArgumentParser.parse_args")
    def test_main_with_default_arguments(self, mock_parse_args, mock_launcher):
        """Test main function with default arguments."""
        # Setup mock args
        mock_args = Mock()
        mock_args.server_class = "mindtrace.services.core.serve.Service"
        mock_args.num_workers = 1
        mock_args.bind = "127.0.0.1:8080"
        mock_args.pid = None
        mock_args.worker_class = "uvicorn.workers.UvicornWorker"
        mock_args.init_params = None
        mock_parse_args.return_value = mock_args

        # Setup mock launcher instance
        mock_launcher_instance = Mock()
        mock_launcher.return_value = mock_launcher_instance

        # Call main
        main()

        # Verify launcher creation and run
        mock_launcher.assert_called_once_with(mock_args)
        mock_launcher_instance.run.assert_called_once()

    @patch("mindtrace.services.core.launcher.Launcher")
    @patch("argparse.ArgumentParser.parse_args")
    def test_main_with_custom_arguments(self, mock_parse_args, mock_launcher):
        """Test main function with custom arguments."""
        # Setup mock args with custom values
        mock_args = Mock()
        mock_args.server_class = "custom.server.CustomServer"
        mock_args.num_workers = 4
        mock_args.bind = "0.0.0.0:9000"
        mock_args.pid = "/var/run/server.pid"
        mock_args.worker_class = "gevent"
        mock_args.init_params = '{"custom": "params"}'
        mock_parse_args.return_value = mock_args

        mock_launcher_instance = Mock()
        mock_launcher.return_value = mock_launcher_instance

        # Call main
        main()

        # Verify launcher creation with custom args
        mock_launcher.assert_called_once_with(mock_args)
        mock_launcher_instance.run.assert_called_once()

    @patch("sys.argv", ["launcher.py", "--help"])
    def test_main_argument_parser_help(self):
        """Test that argument parser can handle help request."""
        with pytest.raises(SystemExit) as exc_info:
            main()
        # Help should exit with code 0
        assert exc_info.value.code == 0

    @patch("mindtrace.services.core.launcher.Launcher")
    @patch("argparse.ArgumentParser.parse_args")
    def test_main_launcher_exception_propagates(self, mock_parse_args, mock_launcher):
        """Test that exceptions from Launcher are propagated."""
        mock_args = Mock()
        mock_parse_args.return_value = mock_args

        # Make Launcher raise an exception
        mock_launcher.side_effect = ValueError("Test error")

        # Exception should propagate
        with pytest.raises(ValueError, match="Test error"):
            main()

    @patch(
        "sys.argv",
        [
            "launcher.py",
            "-s",
            "custom.Server",
            "-w",
            "3",
            "-b",
            "0.0.0.0:8888",
            "-p",
            "/tmp/test.pid",
            "-k",
            "gevent",
            "--init-params",
            '{"test": true}',
        ],
    )
    @patch("mindtrace.services.core.launcher.Launcher")
    def test_main_command_line_parsing(self, mock_launcher):
        """Test that command line arguments are parsed correctly."""
        mock_launcher_instance = Mock()
        mock_launcher.return_value = mock_launcher_instance

        # Call main
        main()

        # Verify launcher was called with parsed args
        mock_launcher.assert_called_once()
        args = mock_launcher.call_args[0][0]

        assert args.server_class == "custom.Server"
        assert args.num_workers == 3
        assert args.bind == "0.0.0.0:8888"
        assert args.pid == "/tmp/test.pid"
        assert args.worker_class == "gevent"
        assert args.init_params == '{"test": true}'

    def test_main_entry_point(self):
        """Test the if __name__ == '__main__' entry point using subprocess."""
        import subprocess
        import sys

        # Test that the script can be executed (will fail due to missing args, but entry point works)
        result = subprocess.run(
            [sys.executable, "mindtrace/services/mindtrace/services/core/launcher.py", "--help"],
            capture_output=True,
            text=True,
        )

        # The script should exit with code 0 for help and show usage information
        assert result.returncode == 0
        assert "MINDTRACE SERVER LAUNCHER" in result.stdout
        assert "usage:" in result.stdout


class TestLauncherIntegration:
    """Integration tests for the Launcher with more realistic scenarios."""

    @patch("mindtrace.services.core.launcher.setup_logger")
    @patch("mindtrace.services.core.launcher.instantiate_target")
    @patch("mindtrace.services.core.launcher.BaseApplication.__init__")
    def test_complex_init_params_parsing(self, mock_base_init, mock_instantiate, mock_setup_logger):
        """Test complex JSON init parameters parsing."""
        complex_params = {
            "database_url": "postgresql://user:pass@localhost/db",
            "redis_config": {"host": "localhost", "port": 6381, "db": 0},
            "feature_flags": ["flag1", "flag2"],
            "timeout": 30.5,
            "debug": True,
        }

        options = Mock()
        options.bind = "127.0.0.1:8080"
        options.num_workers = 1
        options.worker_class = "uvicorn.workers.UvicornWorker"
        options.pid = None
        options.server_class = "test.Server"
        options.init_params = json.dumps(complex_params)

        mock_server = Mock()
        mock_server.unique_name = "test_server"
        mock_server.config = {"MINDTRACE_DIR_PATHS": {"LOGGER_DIR": "/tmp/logs"}}
        mock_server.app = Mock()
        mock_instantiate.return_value = mock_server

        # Create launcher
        Launcher(options)

        # Verify complex params were passed correctly
        mock_instantiate.assert_called_once_with(
            "test.Server",
            database_url="postgresql://user:pass@localhost/db",
            redis_config={"host": "localhost", "port": 6381, "db": 0},
            feature_flags=["flag1", "flag2"],
            timeout=30.5,
            debug=True,
        )
