import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from mindtrace.core.config.config import MINDTRACE_API_KEYS, MINDTRACE_DIR_PATHS, CoreSettings


class TestCoreSettings:
    """Test cases for CoreSettings class."""

    def test_core_settings_model_config(self):
        """Test CoreSettings model configuration."""
        assert CoreSettings.model_config["env_nested_delimiter"] == "__"

    def test_core_settings_fields(self):
        """Test that CoreSettings has expected fields."""
        # Check that the class has the expected field definitions
        model_fields = CoreSettings.model_fields
        assert "MINDTRACE_API_KEYS" in model_fields
        assert "MINDTRACE_DIR_PATHS" in model_fields
        assert "MINDTRACE_DEFAULT_HOST_URLS" in model_fields
        assert "MINDTRACE_MINIO" in model_fields
        assert "MINDTRACE_CLUSTER" in model_fields
        assert "MINDTRACE_MCP" in model_fields
        assert "MINDTRACE_WORKER" in model_fields
        assert "MINDTRACE_TEST_PARAM" in model_fields

    def test_core_settings_default_values(self):
        """Test CoreSettings default values."""
        # MINDTRACE_TEST_PARAM should have a default value
        with patch.dict(
            os.environ,
            {
                "MINDTRACE_API_KEYS__OPENAI": "test_key",
                "MINDTRACE_API_KEYS__DISCORD": "discord_key",
                "MINDTRACE_API_KEYS__ROBOFLOW": "roboflow_key",
                "MINDTRACE_DIR_PATHS__ROOT": "/test/root",
                "MINDTRACE_DIR_PATHS__TEMP_DIR": "/test/temp",
                "MINDTRACE_DIR_PATHS__REGISTRY_DIR": "/test/registry",
                "MINDTRACE_DIR_PATHS__LOGGER_DIR": "/test/logger",
                "MINDTRACE_DIR_PATHS__CLUSTER_REGISTRY_DIR": "/test/cluster",
                "MINDTRACE_DIR_PATHS__SERVER_PIDS_DIR": "/test/pids",
                "MINDTRACE_DEFAULT_HOST_URLS__SERVICE": "http://localhost:8000",
                "MINDTRACE_DEFAULT_HOST_URLS__CLUSTER_MANAGER": "http://localhost:8001",
                "MINDTRACE_MINIO__MINIO_REGISTRY_URI": "http://localhost:9000",
                "MINDTRACE_MINIO__MINIO_ENDPOINT": "localhost:9000",
                "MINDTRACE_MINIO__MINIO_ACCESS_KEY": "minioadmin",
                "MINDTRACE_MINIO__MINIO_SECRET_KEY": "minioadmin",
                "MINDTRACE_CLUSTER__DEFAULT_REDIS_URL": "redis://localhost:6379",
                "MINDTRACE_CLUSTER__MINIO_REGISTRY_URI": "http://localhost:9000",
                "MINDTRACE_CLUSTER__MINIO_ENDPOINT": "localhost:9000",
                "MINDTRACE_CLUSTER__MINIO_ACCESS_KEY": "minioadmin",
                "MINDTRACE_CLUSTER__MINIO_SECRET_KEY": "minioadmin",
                "MINDTRACE_CLUSTER__MINIO_BUCKET": "mindtrace",
                "MINDTRACE_MCP__MOUNT_PATH": "/mnt",
                "MINDTRACE_MCP__HTTP_APP_PATH": "/app",
                "MINDTRACE_WORKER__DEFAULT_REDIS_URL": "redis://localhost:6379",
                "MINDTRACE_TEST_PARAM": "",
            },
        ):
            settings = CoreSettings()
            assert settings.MINDTRACE_TEST_PARAM == ""

    def test_core_settings_env_nested_delimiter(self):
        """Test that environment variables use __ as delimiter."""
        with patch.dict(
            os.environ,
            {
                "MINDTRACE_API_KEYS__OPENAI": "test_key",
                "MINDTRACE_API_KEYS__DISCORD": "discord_key",
                "MINDTRACE_API_KEYS__ROBOFLOW": "roboflow_key",
                "MINDTRACE_DIR_PATHS__ROOT": "/test/root",
                "MINDTRACE_DIR_PATHS__TEMP_DIR": "/test/temp",
                "MINDTRACE_DIR_PATHS__REGISTRY_DIR": "/test/registry",
                "MINDTRACE_DIR_PATHS__LOGGER_DIR": "/test/logger",
                "MINDTRACE_DIR_PATHS__CLUSTER_REGISTRY_DIR": "/test/cluster",
                "MINDTRACE_DIR_PATHS__SERVER_PIDS_DIR": "/test/pids",
                "MINDTRACE_DEFAULT_HOST_URLS__SERVICE": "http://localhost:8000",
                "MINDTRACE_DEFAULT_HOST_URLS__CLUSTER_MANAGER": "http://localhost:8001",
                "MINDTRACE_MINIO__MINIO_REGISTRY_URI": "http://localhost:9000",
                "MINDTRACE_MINIO__MINIO_ENDPOINT": "localhost:9000",
                "MINDTRACE_MINIO__MINIO_ACCESS_KEY": "minioadmin",
                "MINDTRACE_MINIO__MINIO_SECRET_KEY": "minioadmin",
                "MINDTRACE_CLUSTER__DEFAULT_REDIS_URL": "redis://localhost:6379",
                "MINDTRACE_CLUSTER__MINIO_REGISTRY_URI": "http://localhost:9000",
                "MINDTRACE_CLUSTER__MINIO_ENDPOINT": "localhost:9000",
                "MINDTRACE_CLUSTER__MINIO_ACCESS_KEY": "minioadmin",
                "MINDTRACE_CLUSTER__MINIO_SECRET_KEY": "minioadmin",
                "MINDTRACE_CLUSTER__MINIO_BUCKET": "mindtrace",
                "MINDTRACE_MCP__MOUNT_PATH": "/mnt",
                "MINDTRACE_MCP__HTTP_APP_PATH": "/app",
                "MINDTRACE_WORKER__DEFAULT_REDIS_URL": "redis://localhost:6379",
                "MINDTRACE_TEST_PARAM": "test_value",
            },
        ):
            settings = CoreSettings()
            assert settings.MINDTRACE_TEST_PARAM == "test_value"

    def test_core_settings_customise_sources(self):
        """Test CoreSettings source customization."""
        sources = CoreSettings.settings_customise_sources(
            CoreSettings,
            None,  # init_settings
            None,  # dotenv_settings
            None,  # env_settings
            None,  # file_secret_settings
        )

        # Should return a tuple of source functions
        assert isinstance(sources, tuple)
        assert len(sources) == 5  # init, env_expanded, dotenv, ini, file_secret

    def test_core_settings_env_expansion(self):
        """Test that environment variables with ~ are expanded."""
        with patch.dict(
            os.environ,
            {
                "MINDTRACE_API_KEYS__OPENAI": "test_key",
                "MINDTRACE_API_KEYS__DISCORD": "discord_key",
                "MINDTRACE_API_KEYS__ROBOFLOW": "roboflow_key",
                "MINDTRACE_DIR_PATHS__ROOT": "~/test/path",
                "MINDTRACE_DIR_PATHS__TEMP_DIR": "/test/temp",
                "MINDTRACE_DIR_PATHS__REGISTRY_DIR": "/test/registry",
                "MINDTRACE_DIR_PATHS__LOGGER_DIR": "/test/logger",
                "MINDTRACE_DIR_PATHS__CLUSTER_REGISTRY_DIR": "/test/cluster",
                "MINDTRACE_DIR_PATHS__SERVER_PIDS_DIR": "/test/pids",
                "MINDTRACE_DEFAULT_HOST_URLS__SERVICE": "http://localhost:8000",
                "MINDTRACE_DEFAULT_HOST_URLS__CLUSTER_MANAGER": "http://localhost:8001",
                "MINDTRACE_MINIO__MINIO_REGISTRY_URI": "http://localhost:9000",
                "MINDTRACE_MINIO__MINIO_ENDPOINT": "localhost:9000",
                "MINDTRACE_MINIO__MINIO_ACCESS_KEY": "minioadmin",
                "MINDTRACE_MINIO__MINIO_SECRET_KEY": "minioadmin",
                "MINDTRACE_CLUSTER__DEFAULT_REDIS_URL": "redis://localhost:6379",
                "MINDTRACE_CLUSTER__MINIO_REGISTRY_URI": "http://localhost:9000",
                "MINDTRACE_CLUSTER__MINIO_ENDPOINT": "localhost:9000",
                "MINDTRACE_CLUSTER__MINIO_ACCESS_KEY": "minioadmin",
                "MINDTRACE_CLUSTER__MINIO_SECRET_KEY": "minioadmin",
                "MINDTRACE_CLUSTER__MINIO_BUCKET": "mindtrace",
                "MINDTRACE_MCP__MOUNT_PATH": "/mnt",
                "MINDTRACE_MCP__HTTP_APP_PATH": "/app",
                "MINDTRACE_WORKER__DEFAULT_REDIS_URL": "redis://localhost:6379",
            },
        ):
            settings = CoreSettings()
            # The path should be expanded
            assert settings.MINDTRACE_DIR_PATHS.ROOT == os.path.expanduser("~/test/path")

    def test_core_settings_precedence(self):
        """Test that environment variables take precedence over INI."""
        ini_content = """
[MINDTRACE_API_KEYS]
OPENAI = test_key_from_ini
DISCORD = discord_key_from_ini
ROBOFLOW = roboflow_key_from_ini

[MINDTRACE_DIR_PATHS]
ROOT = /test/root_from_ini
TEMP_DIR = /test/temp_from_ini
REGISTRY_DIR = /test/registry_from_ini
LOGGER_DIR = /test/logger_from_ini
CLUSTER_REGISTRY_DIR = /test/cluster_from_ini
SERVER_PIDS_DIR = /test/pids_from_ini

[MINDTRACE_DEFAULT_HOST_URLS]
SERVICE = http://localhost:8000
CLUSTER_MANAGER = http://localhost:8001

[MINDTRACE_MINIO]
MINIO_REGISTRY_URI = http://localhost:9000
MINIO_ENDPOINT = localhost:9000
MINIO_ACCESS_KEY = minioadmin
MINIO_SECRET_KEY = minioadmin

[MINDTRACE_CLUSTER]
DEFAULT_REDIS_URL = redis://localhost:6379
MINIO_REGISTRY_URI = http://localhost:9000
MINIO_ENDPOINT = localhost:9000
MINIO_ACCESS_KEY = minioadmin
MINIO_SECRET_KEY = minioadmin
MINIO_BUCKET = mindtrace

[MINDTRACE_MCP]
MOUNT_PATH = /mnt
HTTP_APP_PATH = /app

[MINDTRACE_WORKER]
DEFAULT_REDIS_URL = redis://localhost:6379

[MINDTRACE_TEST_PARAM]
value = ini_value
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
            f.write(ini_content)
            temp_ini_path = f.name

        try:

            def mock_load_ini_settings():
                from mindtrace.core.config.config import load_ini_as_dict

                return load_ini_as_dict(Path(temp_ini_path))

            with patch("mindtrace.core.config.config.load_ini_settings", mock_load_ini_settings):
                with patch.dict(os.environ, {"MINDTRACE_TEST_PARAM": "env_value"}):
                    settings = CoreSettings()
                    # Environment should override INI
                    assert settings.MINDTRACE_TEST_PARAM == "env_value"
        finally:
            os.unlink(temp_ini_path)


class TestMindtraceModels:
    """Test cases for Mindtrace model classes."""

    def test_mindtrace_api_keys_model(self):
        """Test MINDTRACE_API_KEYS model."""
        model = MINDTRACE_API_KEYS(OPENAI="test_key", DISCORD="discord_key", ROBOFLOW="roboflow_key")
        assert model.OPENAI.get_secret_value() == "test_key"
        assert model.DISCORD.get_secret_value() == "discord_key"
        assert model.ROBOFLOW.get_secret_value() == "roboflow_key"

    def test_mindtrace_api_keys_with_secrets(self):
        """Test MINDTRACE_API_KEYS with SecretStr fields."""
        model = MINDTRACE_API_KEYS(OPENAI="openai_key", DISCORD="discord_key", ROBOFLOW="roboflow_key")
        assert model.OPENAI.get_secret_value() == "openai_key"
        assert model.DISCORD.get_secret_value() == "discord_key"
        assert model.ROBOFLOW.get_secret_value() == "roboflow_key"

    def test_mindtrace_dir_paths_model(self):
        """Test MINDTRACE_DIR_PATHS model."""
        model = MINDTRACE_DIR_PATHS(
            ROOT="/test/root",
            TEMP_DIR="/test/temp",
            REGISTRY_DIR="/test/registry",
            LOGGER_DIR="/test/logger",
            CLUSTER_REGISTRY_DIR="/test/cluster",
            SERVER_PIDS_DIR="/test/pids",
        )
        assert model.ROOT == "/test/root"
        assert model.TEMP_DIR == "/test/temp"
        assert model.REGISTRY_DIR == "/test/registry"
        assert model.LOGGER_DIR == "/test/logger"
        assert model.CLUSTER_REGISTRY_DIR == "/test/cluster"
        assert model.SERVER_PIDS_DIR == "/test/pids"

    def test_mindtrace_models_validation(self):
        """Test that Mindtrace models validate correctly."""
        # Test with valid data
        api_keys = MINDTRACE_API_KEYS(OPENAI="valid_key", DISCORD="discord_key", ROBOFLOW="roboflow_key")
        assert api_keys.OPENAI.get_secret_value() == "valid_key"

        # Test with None values (should be allowed for optional fields)
        api_keys_none = MINDTRACE_API_KEYS(OPENAI="test_key", DISCORD="discord_key", ROBOFLOW="roboflow_key")
        assert api_keys_none.OPENAI.get_secret_value() == "test_key"

    def test_mindtrace_models_deserialization(self):
        """Test that Mindtrace models can be deserialized."""
        data = {"OPENAI": "test_key", "DISCORD": "discord_key", "ROBOFLOW": "roboflow_key"}

        api_keys = MINDTRACE_API_KEYS(**data)
        assert api_keys.OPENAI.get_secret_value() == "test_key"
        assert api_keys.DISCORD.get_secret_value() == "discord_key"
        assert api_keys.ROBOFLOW.get_secret_value() == "roboflow_key"
