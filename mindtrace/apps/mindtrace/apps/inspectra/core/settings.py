from typing import Optional

from pydantic import BaseModel, SecretStr

from mindtrace.core import Config


class InspectraSettings(BaseModel):
    """Inspectra service configuration settings."""

    # Service URL
    URL: str = "http://localhost:8080"

    # Database
    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB: str = "inspectra"

    # Auth / JWT
    JWT_SECRET: SecretStr = SecretStr("dev-secret-key")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRES_IN: int = 60 * 60  # seconds

    # Misc
    AUTH_ENABLED: bool = False
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = False


_config: Optional[Config] = None


def get_inspectra_config() -> Config:
    """Load cached Config with INSPECTRA__ env override support."""
    global _config
    if _config is None:
        _config = Config.load(defaults={"INSPECTRA": InspectraSettings().model_dump()})
    return _config


def reset_inspectra_config() -> None:
    """Reset config cache (useful in tests)."""
    global _config
    _config = None
