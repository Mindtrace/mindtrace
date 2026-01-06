"""Configuration for the Horizon service.

Uses mindtrace.core.Config pattern with automatic environment variable support.
Environment variables use HORIZON__ prefix (e.g., HORIZON__URL=http://0.0.0.0:8081).

Example:
    ```python
    from mindtrace.apps.horizon import HorizonService, HorizonConfig

    # Default settings (reads from env vars automatically)
    service = HorizonService()
    print(service.config.HORIZON.URL)

    # With overrides
    config = HorizonConfig(DEBUG=True, MONGO_DB="custom")
    service = HorizonService(config_overrides=config)
    ```
"""

from typing import Optional

from pydantic import BaseModel, SecretStr

from mindtrace.core.config import Config


class HorizonSettings(BaseModel):
    """Horizon service configuration settings."""

    URL: str = "http://localhost:8080"
    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB: str = "horizon"
    AUTH_ENABLED: bool = False
    AUTH_SECRET_KEY: Optional[SecretStr] = SecretStr("dev-secret-key")
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = False


class HorizonConfig(Config):
    """Config with HorizonSettings under HORIZON namespace.

    Supports HORIZON__* environment variables automatically.

    Example:
        config = HorizonConfig()                    # defaults + env vars
        config = HorizonConfig(DEBUG=True)          # override DEBUG
        config.HORIZON.URL                          # access settings
        config.get_secret("HORIZON", "AUTH_SECRET_KEY")  # get secret
    """

    def __init__(self, **overrides):
        settings = HorizonSettings(**overrides) if overrides else HorizonSettings()
        super().__init__({"HORIZON": settings.model_dump()}, apply_env_overrides=True)
