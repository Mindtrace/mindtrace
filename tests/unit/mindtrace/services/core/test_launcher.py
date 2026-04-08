import importlib.util
import json
import platform
import runpy
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, call, patch

import pytest

import mindtrace.services.core.launcher as launcher_module
from mindtrace.services.core.launcher import Launcher, main

LAUNCHER_PATH = Path(launcher_module.__file__)


def _load_launcher_for_os(monkeypatch: pytest.MonkeyPatch, os_name: str):
    monkeypatch.setattr(platform, "system", lambda: os_name)

    if os_name != "Windows":
        gunicorn_module = ModuleType("gunicorn")
        gunicorn_app_module = ModuleType("gunicorn.app")
        gunicorn_base_module = ModuleType("gunicorn.app.base")

        class FakeBaseApplication:
            def __init__(self, *args, **kwargs):
                pass

            def run(self):
                pass

        gunicorn_base_module.BaseApplication = FakeBaseApplication
        monkeypatch.setitem(sys.modules, "gunicorn", gunicorn_module)
        monkeypatch.setitem(sys.modules, "gunicorn.app", gunicorn_app_module)
        monkeypatch.setitem(sys.modules, "gunicorn.app.base", gunicorn_base_module)

    spec = importlib.util.spec_from_file_location(f"_test_launcher_{os_name.lower()}", LAUNCHER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(launcher_module.IS_WINDOWS, reason="These tests exercise the native non-Windows launcher import.")
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
    def test_launcher_init_with_init_params(self, mock_base_init, mock_instantiate, mock_options, mock_server):
        """Test Launcher initialization with init parameters."""
        # Setup mocks
        mock_instantiate.return_value = mock_server

        # Server instantiation is deferred to load(); application is None until then
        launcher = Launcher(mock_options)
        assert launcher.application is None
        mock_instantiate.assert_not_called()

        # Verify gunicorn options are set correctly
        expected_options = {
            "bind": "127.0.0.1:8080",
            "workers": 2,
            "worker_class": "uvicorn.workers.UvicornWorker",
            "pidfile": "/tmp/test.pid",
        }
        assert launcher.gunicorn_options == expected_options

        launcher.load()

        # Verify server instantiation happened in load()
        mock_instantiate.assert_called_once_with(
            "test.server.TestServer", param1="value1", param2=42, pid_file="/tmp/test.pid"
        )

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

        launcher = Launcher(options)
        launcher.load()

        # Verify server instantiation with no init params
        mock_instantiate.assert_called_once_with("default.Server", pid_file=None)

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

        launcher = Launcher(options)
        launcher.load()

        # Verify server instantiation with empty init params
        mock_instantiate.assert_called_once_with("test.Server", pid_file=None)

    @patch("mindtrace.services.core.launcher.instantiate_target")
    @patch("mindtrace.services.core.launcher.BaseApplication.__init__")
    def test_launcher_init_invalid_json(self, mock_base_init, mock_instantiate):
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
        """Test the if __name__ == '__main__' entry point with run_path."""
        mock_args = Mock()
        mock_args.server_class = "test.Server"
        mock_args.num_workers = 1
        mock_args.bind = "127.0.0.1:8080"
        mock_args.pid = None
        mock_args.worker_class = "uvicorn.workers.UvicornWorker"
        mock_args.init_params = None

        with patch("argparse.ArgumentParser.parse_args", return_value=mock_args):
            if launcher_module.IS_WINDOWS:
                mock_server = Mock()
                mock_server.unique_name = "test_server"
                mock_server.config = {"MINDTRACE_DIR_PATHS": {"LOGGER_DIR": "/tmp/logs"}}
                mock_server.app = Mock()
                uvicorn_module = ModuleType("uvicorn")
                uvicorn_module.run = Mock()

                with (
                    patch("mindtrace.core.instantiate_target", return_value=mock_server),
                    patch("mindtrace.core.setup_logger", return_value=Mock()),
                    patch.dict(sys.modules, {"uvicorn": uvicorn_module}),
                ):
                    runpy.run_path(str(LAUNCHER_PATH), run_name="__main__")

                uvicorn_module.run.assert_called_once()
            else:
                with (
                    patch("gunicorn.app.base.BaseApplication.__init__", return_value=None),
                    patch("gunicorn.app.base.BaseApplication.run", autospec=True) as mock_run,
                ):
                    runpy.run_path(str(LAUNCHER_PATH), run_name="__main__")

                mock_run.assert_called_once()

    def test_main_entry_point_direct(self):
        """Test that if __name__ == '__main__' calls main()."""
        import mindtrace.services.core.launcher as launcher_module

        # Simulate running as main by directly calling the code path
        # We can't easily test the actual if __name__ == "__main__" without importing differently,
        # but we can verify the main function exists and is callable
        assert callable(launcher_module.main)

        # Test that main can be called (which would happen in __main__ block)
        with patch("mindtrace.services.core.launcher.Launcher") as mock_launcher:
            mock_args = Mock()
            mock_args.server_class = "test.Server"
            mock_args.num_workers = 1
            mock_args.bind = "127.0.0.1:8080"
            mock_args.pid = None
            mock_args.worker_class = "uvicorn.workers.UvicornWorker"
            mock_args.init_params = None
            with patch("argparse.ArgumentParser.parse_args", return_value=mock_args):
                launcher_module.main()
                mock_launcher.return_value.run.assert_called_once()


@pytest.mark.skipif(launcher_module.IS_WINDOWS, reason="These tests exercise the native non-Windows launcher import.")
class TestLauncherIntegration:
    """Integration tests for the Launcher with more realistic scenarios."""

    @patch("mindtrace.services.core.launcher.instantiate_target")
    @patch("mindtrace.services.core.launcher.BaseApplication.__init__")
    def test_complex_init_params_parsing(self, mock_base_init, mock_instantiate):
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

        launcher = Launcher(options)
        launcher.load()

        # Verify complex params were passed correctly
        mock_instantiate.assert_called_once_with(
            "test.Server",
            database_url="postgresql://user:pass@localhost/db",
            redis_config={"host": "localhost", "port": 6381, "db": 0},
            feature_flags=["flag1", "flag2"],
            timeout=30.5,
            debug=True,
            pid_file=None,
        )


class TestLauncherCrossPlatformReloaded:
    def test_non_windows_launcher_loads_application(self, monkeypatch):
        module = _load_launcher_for_os(monkeypatch, "Linux")
        options = Mock(
            bind="127.0.0.1:8080",
            num_workers=2,
            worker_class="uvicorn.workers.UvicornWorker",
            pid="/tmp/test.pid",
            server_class="test.server.TestServer",
            init_params='{"param1": "value1"}',
        )
        mock_server = Mock()
        mock_server.unique_name = "test_server"
        mock_server.config = {"MINDTRACE_DIR_PATHS": {"LOGGER_DIR": "/tmp/logs"}}
        mock_server.app = Mock()

        with (
            patch.object(module, "instantiate_target", return_value=mock_server) as mock_instantiate,
            patch.object(module, "setup_logger", return_value=Mock()),
            patch.object(module.BaseApplication, "__init__", return_value=None),
        ):
            launcher = module.Launcher(options)
            result = launcher.load()

        mock_instantiate.assert_called_once_with("test.server.TestServer", pid_file="/tmp/test.pid", param1="value1")
        assert result == mock_server.app
        assert launcher.application == mock_server.app

    def test_non_windows_launcher_load_config_sets_supported_values(self, monkeypatch):
        module = _load_launcher_for_os(monkeypatch, "Linux")
        options = Mock(
            bind="0.0.0.0:9000",
            num_workers=1,
            worker_class="sync",
            pid=None,
            server_class="test.Server",
            init_params=None,
        )

        with patch.object(module.BaseApplication, "__init__", return_value=None):
            launcher = module.Launcher(options)

        launcher.cfg = Mock()
        launcher.cfg.settings = {"bind": Mock(), "workers": Mock(), "worker_class": Mock(), "pidfile": Mock()}

        launcher.load_config()

        launcher.cfg.set.assert_has_calls(
            [call("bind", "0.0.0.0:9000"), call("workers", 1), call("worker_class", "sync")],
            any_order=True,
        )
        assert launcher.cfg.set.call_count == 3

    def test_windows_launcher_initializes_and_runs_uvicorn(self, monkeypatch):
        module = _load_launcher_for_os(monkeypatch, "Windows")
        options = Mock(
            bind="0.0.0.0:9090",
            num_workers=3,
            worker_class="ignored",
            pid="/tmp/test.pid",
            server_class="test.server.TestServer",
            init_params='{"debug": true}',
        )
        mock_server = Mock()
        mock_server.unique_name = "test_server"
        mock_server.config = {"MINDTRACE_DIR_PATHS": {"LOGGER_DIR": "/tmp/logs"}}
        mock_server.app = Mock()
        uvicorn_module = ModuleType("uvicorn")
        uvicorn_module.run = Mock()
        monkeypatch.setitem(sys.modules, "uvicorn", uvicorn_module)

        with (
            patch.object(module, "instantiate_target", return_value=mock_server) as mock_instantiate,
            patch.object(module, "setup_logger", return_value=Mock()),
        ):
            launcher = module.Launcher(options)
            launcher.run()

        mock_instantiate.assert_called_once_with("test.server.TestServer", pid_file="/tmp/test.pid", debug=True)
        assert launcher.application == mock_server.app
        assert launcher.uvicorn_config == {
            "app": mock_server.app,
            "host": "0.0.0.0",
            "port": 9090,
            "workers": 3,
        }
        uvicorn_module.run.assert_called_once_with(**launcher.uvicorn_config)
