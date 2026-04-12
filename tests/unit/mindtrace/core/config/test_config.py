"""Tests for Config and ConfigModel."""

import os
from unittest.mock import patch

import pytest
from pydantic import SecretStr

from mindtrace.core.config import Config, ConfigModel


class TestConfigModel:
    """Tests for the ConfigModel base class."""

    def test_getitem(self):
        """Test dict-style access via __getitem__."""

        class MyModel(ConfigModel):
            name: str = "test"
            count: int = 42

        m = MyModel()
        assert m["name"] == "test"
        assert m["count"] == 42

    def test_getitem_missing_key(self):
        """Test that missing keys raise AttributeError."""

        class MyModel(ConfigModel):
            name: str = "test"

        m = MyModel()
        with pytest.raises(AttributeError):
            m["nonexistent"]

    def test_get_with_default(self):
        """Test .get() with fallback default."""

        class MyModel(ConfigModel):
            name: str = "test"

        m = MyModel()
        assert m.get("name") == "test"
        assert m.get("missing", "fallback") == "fallback"

    def test_tilde_expansion(self):
        """Test that ~ in string fields is expanded."""

        class MyModel(ConfigModel):
            path: str = "~/some/path"
            other: str = "no-tilde"

        m = MyModel()
        assert not m.path.startswith("~")
        assert m.path == os.path.expanduser("~/some/path")
        assert m.other == "no-tilde"

    def test_tilde_expansion_skips_secrets(self):
        """Test that SecretStr fields are not affected by tilde expansion."""

        class MyModel(ConfigModel):
            token: SecretStr = SecretStr("~/not-a-path")

        m = MyModel()
        assert m.token.get_secret_value() == "~/not-a-path"

    def test_nested_getitem(self):
        """Test nested dict-style access config['SECTION']['KEY']."""

        class Inner(ConfigModel):
            key: str = "value"

        class Outer(ConfigModel):
            section: Inner = Inner()

        o = Outer()
        assert o["section"]["key"] == "value"

    def test_reveal_secrets_serializer(self):
        """Test that secrets are revealed in JSON serialization."""

        class MyModel(ConfigModel):
            token: SecretStr = SecretStr("my-secret")
            name: str = "public"

        m = MyModel()
        # Default repr masks the secret
        assert "**********" in repr(m.token)
        # JSON serialization reveals the secret
        data = m.model_dump(mode="json")
        assert data["token"] == "my-secret"
        assert data["name"] == "public"


class TestConfigGetSecret:
    """Tests for Config.get_secret()."""

    def test_get_secret_returns_value(self):
        """Test retrieving a secret by path."""
        settings = Config()
        # The INI file provides placeholder values for API keys
        result = settings.get_secret("MINDTRACE_API_KEYS", "OPENAI")
        assert result is not None
        assert isinstance(result, str)

    def test_get_secret_missing_path(self):
        """Test that missing path returns None."""
        settings = Config()
        assert settings.get_secret("NONEXISTENT", "KEY") is None

    def test_get_secret_partial_path(self):
        """Test that partial path returns None for missing leaf."""
        settings = Config()
        assert settings.get_secret("MINDTRACE_API_KEYS", "NONEXISTENT") is None

    def test_get_secret_non_secret_field(self):
        """Test that non-secret fields return string representation."""
        settings = Config()
        result = settings.get_secret("MINDTRACE_DIR_PATHS", "ROOT")
        assert result is not None
        assert isinstance(result, str)


class TestConfigDictAccess:
    """Tests for dict-style access on Config."""

    def test_top_level_getitem(self):
        """Test config['SECTION'] returns a ConfigModel."""
        settings = Config()
        section = settings["MINDTRACE_DIR_PATHS"]
        assert hasattr(section, "ROOT")
        assert hasattr(section, "TEMP_DIR")

    def test_nested_getitem(self):
        """Test config['SECTION']['KEY'] returns the value."""
        settings = Config()
        value = settings["MINDTRACE_DEFAULT_HOST_URLS"]["SERVICE"]
        assert isinstance(value, str)
        assert "://" in value  # Should be a URL

    def test_get_with_default(self):
        """Test .get() on Config with default."""
        settings = Config()
        assert settings.get("NONEXISTENT", {}) == {}
        assert settings.get("MINDTRACE_DIR_PATHS") is not None

    def test_attribute_access(self):
        """Test attribute-style access."""
        settings = Config()
        assert isinstance(settings.MINDTRACE_DIR_PATHS.ROOT, str)
        assert isinstance(settings.MINDTRACE_CLUSTER.RABBITMQ_PORT, int)
        assert isinstance(settings.MINDTRACE_LOGGER.USE_STRUCTLOG, bool)

    def test_env_override(self):
        """Test that env vars override INI values."""
        with patch.dict(os.environ, {"MINDTRACE_TEST_PARAM": "from_env"}):
            settings = Config()
            assert settings.MINDTRACE_TEST_PARAM == "from_env"

    def test_tilde_expansion_in_paths(self):
        """Test that ~ is expanded in directory paths."""
        settings = Config()
        root = settings.MINDTRACE_DIR_PATHS.ROOT
        assert "~" not in root


class TestConfigFields:
    """Tests for Config class fields and structure."""

    def test_model_config(self):
        """Test Config model configuration."""
        assert Config.model_config["env_nested_delimiter"] == "__"

    def test_expected_fields(self):
        """Test that Config has expected fields."""
        model_fields = Config.model_fields
        assert "MINDTRACE_API_KEYS" in model_fields
        assert "MINDTRACE_TESTING_API_KEYS" in model_fields
        assert "MINDTRACE_DIR_PATHS" in model_fields
        assert "MINDTRACE_DEFAULT_HOST_URLS" in model_fields
        assert "MINDTRACE_MINIO" in model_fields
        assert "MINDTRACE_CLUSTER" in model_fields
        assert "MINDTRACE_MCP" in model_fields
        assert "MINDTRACE_WORKER" in model_fields
        assert "MINDTRACE_TEST_PARAM" in model_fields
        assert "MINDTRACE_LOGGER" in model_fields

    def test_default_values(self):
        """Test Config default values from INI."""
        with patch.dict(os.environ, {"MINDTRACE_TEST_PARAM": ""}):
            settings = Config()
            assert settings.MINDTRACE_TEST_PARAM == ""

    def test_customise_sources(self):
        """Test Config source customization."""
        sources = Config.settings_customise_sources(
            Config,
            None,  # init_settings
            None,  # dotenv_settings
            None,  # env_settings
            None,  # file_secret_settings
        )
        assert isinstance(sources, tuple)
        assert len(sources) == 5  # init, env, dotenv, ini, file_secret

    def test_env_nested_delimiter(self):
        """Test that environment variables use __ as delimiter."""
        with patch.dict(os.environ, {"MINDTRACE_TEST_PARAM": "test_value"}):
            settings = Config()
            assert settings.MINDTRACE_TEST_PARAM == "test_value"

    def test_env_expansion(self):
        """Test that environment variables with ~ are expanded."""
        with patch.dict(os.environ, {"MINDTRACE_DIR_PATHS__ROOT": "~/test/path"}):
            settings = Config()
            assert settings.MINDTRACE_DIR_PATHS.ROOT == os.path.expanduser("~/test/path")

    def test_precedence(self):
        """Test that environment variables take precedence over INI."""
        import tempfile
        from pathlib import Path

        ini_content = """
[MINDTRACE_API_KEYS]
OPENAI = test_key_from_ini
DISCORD = discord_key_from_ini
ROBOFLOW = roboflow_key_from_ini

[MINDTRACE_TESTING_API_KEYS]
DISCORD = test_discord_key_from_ini

[MINDTRACE_DIR_PATHS]
ROOT = /test/root_from_ini
TEMP_DIR = /test/temp_from_ini
REGISTRY_DIR = /test/registry_from_ini
LOGGER_DIR = /test/logger_from_ini
STRUCT_LOGGER_DIR = /test/structlog_from_ini
CLUSTER_REGISTRY_DIR = /test/cluster_from_ini
SERVER_PIDS_DIR = /test/pids_from_ini
ORCHESTRATOR_LOCAL_CLIENT_DIR = /test/orchestrator_from_ini

[MINDTRACE_LOGGER]
USE_STRUCTLOG = True

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
MINIO_HOST = localhost
MINIO_PORT = 9000
MINIO_ACCESS_KEY = minioadmin
MINIO_SECRET_KEY = minioadmin
MINIO_BUCKET = mindtrace
RABBITMQ_PORT = 5672
RABBITMQ_HOST = localhost
RABBITMQ_USERNAME = user
RABBITMQ_PASSWORD = password
WORKER_PORTS_RANGE = 8090-8100

[MINDTRACE_MCP]
MOUNT_PATH = /mnt
HTTP_APP_PATH = /app

[MINDTRACE_WORKER]
DEFAULT_REDIS_URL = redis://localhost:6379

[MINDTRACE_GCP]
GCP_PROJECT_ID = test-project
GCP_BUCKET_NAME = test-bucket
GCP_CREDENTIALS_PATH = /path/to/credentials.json
GCP_LOCATION = us-central1
GCP_STORAGE_CLASS = STANDARD

[MINDTRACE_GCP_REGISTRY]
GCP_REGISTRY_URI = https://storage.googleapis.com
GCP_BUCKET_NAME = test-bucket

[MINDTRACE_TEST_PARAM]
value = ini_value
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
            f.write(ini_content)
            temp_ini_path = f.name

        try:

            def mock_load_ini_settings():
                from mindtrace.core.utils import load_ini_as_dict

                return load_ini_as_dict(Path(temp_ini_path))

            with patch("mindtrace.core.config.config.load_ini_settings", mock_load_ini_settings):
                with patch.dict(
                    os.environ,
                    {
                        "MINDTRACE_TEST_PARAM": "env_value",
                        "MINDTRACE_TESTING_API_KEYS__DISCORD": "test_discord_key_from_env",
                    },
                ):
                    settings = Config()
                    # Environment should override INI
                    assert settings.MINDTRACE_TEST_PARAM == "env_value"
        finally:
            os.unlink(temp_ini_path)


class TestMindtraceModels:
    """Test cases for Mindtrace section model classes."""

    def test_mindtrace_api_keys_model(self):
        """Test MINDTRACE_API_KEYS model."""
        from mindtrace.core.config.config import MINDTRACE_API_KEYS

        model = MINDTRACE_API_KEYS(OPENAI="test_key", DISCORD="discord_key", ROBOFLOW="roboflow_key")
        assert model.OPENAI.get_secret_value() == "test_key"
        assert model.DISCORD.get_secret_value() == "discord_key"
        assert model.ROBOFLOW.get_secret_value() == "roboflow_key"

    def test_mindtrace_dir_paths_model(self):
        """Test MINDTRACE_DIR_PATHS model."""
        from mindtrace.core.config.config import MINDTRACE_DIR_PATHS

        model = MINDTRACE_DIR_PATHS(
            ROOT="/test/root",
            TEMP_DIR="/test/temp",
            REGISTRY_DIR="/test/registry",
            LOGGER_DIR="/test/logger",
            STRUCT_LOGGER_DIR="/test/structlog",
            CLUSTER_REGISTRY_DIR="/test/cluster",
            SERVER_PIDS_DIR="/test/pids",
            ORCHESTRATOR_LOCAL_CLIENT_DIR="/test/orchestrator",
        )
        assert model.ROOT == "/test/root"
        assert model.TEMP_DIR == "/test/temp"

    def test_mindtrace_testing_api_keys_model(self):
        """Test MINDTRACE_TESTING_API_KEYS model."""
        from mindtrace.core.config.config import MINDTRACE_TESTING_API_KEYS

        model = MINDTRACE_TESTING_API_KEYS(DISCORD="test_discord_key")
        assert model.DISCORD.get_secret_value() == "test_discord_key"

        model_none = MINDTRACE_TESTING_API_KEYS(DISCORD=None)
        assert model_none.DISCORD is None

    def test_mindtrace_models_deserialization(self):
        """Test that Mindtrace models can be deserialized."""
        from mindtrace.core.config.config import MINDTRACE_API_KEYS

        data = {"OPENAI": "test_key", "DISCORD": "discord_key", "ROBOFLOW": "roboflow_key"}
        api_keys = MINDTRACE_API_KEYS(**data)
        assert api_keys.OPENAI.get_secret_value() == "test_key"
        assert api_keys.DISCORD.get_secret_value() == "discord_key"
        assert api_keys.ROBOFLOW.get_secret_value() == "roboflow_key"

    def test_section_models_are_config_model(self):
        """Test that section models inherit from ConfigModel."""
        from mindtrace.core.config.config import MINDTRACE_API_KEYS, MINDTRACE_DIR_PATHS

        assert issubclass(MINDTRACE_API_KEYS, ConfigModel)
        assert issubclass(MINDTRACE_DIR_PATHS, ConfigModel)

    def test_section_model_dict_access(self):
        """Test that section models support dict-style access."""
        from mindtrace.core.config.config import MINDTRACE_DIR_PATHS

        model = MINDTRACE_DIR_PATHS(
            ROOT="/test/root",
            TEMP_DIR="/test/temp",
            REGISTRY_DIR="/test/registry",
            LOGGER_DIR="/test/logger",
            STRUCT_LOGGER_DIR="/test/structlog",
            CLUSTER_REGISTRY_DIR="/test/cluster",
            SERVER_PIDS_DIR="/test/pids",
            ORCHESTRATOR_LOCAL_CLIENT_DIR="/test/orchestrator",
        )
        assert model["ROOT"] == "/test/root"
        assert model.get("TEMP_DIR") == "/test/temp"
        assert model.get("MISSING", "default") == "default"


class TestCoreConfigAlias:
    """Test that CoreConfig alias works."""

    def test_core_config_is_config(self):
        """Test that CoreConfig is an alias for Config."""
        from mindtrace.core.config import CoreConfig

        assert CoreConfig is Config

    def test_core_config_importable_from_core(self):
        """Test that CoreConfig is importable from mindtrace.core."""
        from mindtrace.core import CoreConfig

        assert CoreConfig is Config
