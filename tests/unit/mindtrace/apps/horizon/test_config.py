"""Unit tests for Horizon configuration."""

from mindtrace.apps.horizon.config import HorizonConfig, HorizonSettings
from mindtrace.core import Config


class TestHorizonSettings:
    """Tests for HorizonSettings Pydantic model."""

    def test_default_values(self):
        """Test that HorizonSettings has sensible defaults."""
        settings = HorizonSettings()

        assert settings.URL == "http://localhost:8080"
        assert settings.MONGO_URI == "mongodb://localhost:27017"
        assert settings.MONGO_DB == "horizon"
        assert settings.AUTH_ENABLED is False
        assert settings.LOG_LEVEL == "INFO"
        assert settings.DEBUG is False

    def test_custom_values(self):
        """Test that HorizonSettings accepts custom values."""
        settings = HorizonSettings(
            URL="http://0.0.0.0:9000",
            MONGO_URI="mongodb://mongo:27017",
            MONGO_DB="custom_db",
            AUTH_ENABLED=True,
            LOG_LEVEL="DEBUG",
            DEBUG=True,
        )

        assert settings.URL == "http://0.0.0.0:9000"
        assert settings.MONGO_URI == "mongodb://mongo:27017"
        assert settings.AUTH_ENABLED is True


class TestHorizonConfig:
    """Tests for HorizonConfig class."""

    def test_is_config_subclass(self):
        """Test that HorizonConfig is a Config subclass."""
        config = HorizonConfig()
        assert isinstance(config, Config)

    def test_has_horizon_section(self):
        """Test that config has HORIZON section with expected keys."""
        config = HorizonConfig()

        assert "HORIZON" in config
        horizon = config["HORIZON"]

        assert "URL" in horizon
        assert "MONGO_URI" in horizon
        assert "MONGO_DB" in horizon
        assert "AUTH_ENABLED" in horizon

    def test_attribute_access(self):
        """Test that config supports attribute access."""
        config = HorizonConfig()

        assert config.HORIZON.URL == "http://localhost:8080"
        assert config.HORIZON.MONGO_DB == "horizon"

    def test_dict_access(self):
        """Test that config supports dict access."""
        config = HorizonConfig()

        assert config["HORIZON"]["URL"] == "http://localhost:8080"
        assert config["HORIZON"]["MONGO_DB"] == "horizon"

    def test_with_overrides(self):
        """Test config with overrides."""
        config = HorizonConfig(DEBUG=True, MONGO_DB="custom")

        assert config.HORIZON.DEBUG == "True"  # Note: becomes string after Config processing
        assert config.HORIZON.MONGO_DB == "custom"
        # Default values still present
        assert config.HORIZON.URL == "http://localhost:8080"

    def test_env_override(self, env_override):
        """Test that environment variables override config values."""
        env_override.set(HORIZON__URL="http://0.0.0.0:9999", HORIZON__MONGO_DB="env_db")

        config = HorizonConfig()

        assert config.HORIZON.URL == "http://0.0.0.0:9999"
        assert config.HORIZON.MONGO_DB == "env_db"

    def test_secret_key_is_masked(self):
        """Test that AUTH_SECRET_KEY is masked in normal access."""
        config = HorizonConfig()

        # Secret fields should be masked
        assert config.HORIZON.AUTH_SECRET_KEY == "********"

    def test_secret_key_retrievable(self):
        """Test that AUTH_SECRET_KEY can be retrieved via get_secret."""
        config = HorizonConfig()

        secret = config.get_secret("HORIZON", "AUTH_SECRET_KEY")
        assert secret == "dev-secret-key"

    def test_clone_with_overrides(self):
        """Test cloning config with overrides doesn't affect original."""
        original = HorizonConfig()
        cloned = original.clone_with_overrides({"HORIZON": {"URL": "http://cloned:8080"}})

        assert original.HORIZON.URL == "http://localhost:8080"
        assert cloned.HORIZON.URL == "http://cloned:8080"

    def test_multiple_configs_are_independent(self):
        """Test that multiple HorizonConfig instances are independent."""
        config1 = HorizonConfig(MONGO_DB="db1")
        config2 = HorizonConfig(MONGO_DB="db2")

        assert config1.HORIZON.MONGO_DB == "db1"
        assert config2.HORIZON.MONGO_DB == "db2"
