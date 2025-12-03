"""Configuration for the Horizon service.

Uses mindtrace.core.Config for environment variable override support.
Environment variables use HORIZON__ prefix (e.g., HORIZON__URL=http://0.0.0.0:8081).
"""

from typing import Optional

from pydantic import BaseModel, SecretStr

from mindtrace.core import Config


class HorizonSettings(BaseModel):
    """Horizon service configuration settings."""

    # Service URL (e.g., http://localhost:8080)
    URL: str = "http://localhost:8080"

    # MongoDB connection
    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB: str = "horizon"

    # Authentication
    AUTH_ENABLED: bool = False
    AUTH_SECRET_KEY: Optional[SecretStr] = SecretStr("dev-secret-key")

    # Logging
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = False


# Module-level config cache
_config: Optional[Config] = None


def get_horizon_config() -> Config:
    """Get the Horizon configuration singleton.

    Configuration is loaded once and cached. Supports environment variable
    overrides using HORIZON__ prefix.

    Examples:
        ```bash
        export HORIZON__URL=http://0.0.0.0:8081
        export HORIZON__MONGO_URI=mongodb://mongo:27017
        ```

        ```python
        config = get_horizon_config()
        print(config.HORIZON.URL)  # http://localhost:8080
        ```

    Returns:
        Config instance with HORIZON section containing all settings.
    """
    global _config
    if _config is None:
        _config = Config.load(defaults={"HORIZON": HorizonSettings().model_dump()})
    return _config


def reset_horizon_config() -> None:
    """Reset the config cache. Useful for testing."""
    global _config
    _config = None

