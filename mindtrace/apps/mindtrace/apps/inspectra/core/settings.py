"""
Inspectra configuration and settings.

Loads INSPECTRA settings from env (with INSPECTRA__ prefix support) and from
.env files in the inspectra app dir and cwd. Provides get_inspectra_config()
for a cached Config instance.
"""

import os
from pathlib import Path
from typing import Optional

import dotenv
from pydantic import BaseModel, SecretStr

from mindtrace.core import Config


def _load_inspectra_dotenv() -> None:
    """Load .env from the inspectra app dir and cwd so MONGO_URI etc. are set."""
    app_dir = Path(__file__).resolve().parent.parent
    dotenv.load_dotenv(app_dir / ".env")
    dotenv.load_dotenv()  # cwd


class InspectraSettings(BaseModel):
    """Inspectra service configuration.

    Defaults are overridden by env (INSPECTRA__* or unprefixed for MONGO_URI,
    MONGO_DB_NAME, CORS_ALLOW_ORIGINS). Used as the INSPECTRA section of Config.
    """

    # Service URL (host:port).
    URL: str = "http://0.0.0.0:8080"

    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "inspectra"

    # Auth / JWT
    JWT_SECRET: SecretStr = SecretStr("dev-secret-key")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRES_IN: int = 15 * 60  # access token TTL in seconds (900 = 15 min)
    REFRESH_TOKEN_EXPIRES_IN: int = 7 * 24 * 60 * 60  # refresh token TTL (604800 = 7 days)

    # Password rules
    PASSWORD_MIN_LENGTH: int = 12
    PBKDF2_ITERATIONS: int = 100_000  # PBKDF2-HMAC-SHA256 iterations (tune for perf vs security)

    # CORS: comma-separated origins, or '*' to allow all origins
    CORS_ALLOW_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Misc
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = False


_config: Optional[Config] = None


def get_inspectra_config() -> Config:
    """Load or return the cached Config with INSPECTRA settings.

    On first call, loads .env from the inspectra app dir and cwd, then builds
    Config with INSPECTRA defaults. Env overrides: INSPECTRA__* and unprefixed
    MONGO_URI, MONGO_DB_NAME, CORS_ALLOW_ORIGINS (e.g. for Docker).

    Returns:
        Config instance with INSPECTRA attribute holding InspectraSettings.
    """
    global _config
    if _config is None:
        _load_inspectra_dotenv()
        defaults = InspectraSettings().model_dump()
        # Fallbacks for docker / plain env (unprefixed vars from .env)
        if "MONGO_URI" in os.environ:
            defaults["MONGO_URI"] = os.environ["MONGO_URI"]
        if "MONGO_DB_NAME" in os.environ:
            defaults["MONGO_DB_NAME"] = os.environ["MONGO_DB_NAME"]
        if "CORS_ALLOW_ORIGINS" in os.environ:
            defaults["CORS_ALLOW_ORIGINS"] = os.environ["CORS_ALLOW_ORIGINS"]
        for key in ("JWT_EXPIRES_IN", "REFRESH_TOKEN_EXPIRES_IN"):
            if key in os.environ:
                try:
                    defaults[key] = int(os.environ[key])
                except ValueError:
                    pass
        _config = Config.load(defaults={"INSPECTRA": defaults})
    return _config


def reset_inspectra_config() -> None:
    """Reset the cached config so the next get_inspectra_config() reloads from env.

    Intended for tests that change env or need a fresh config.
    """
    global _config
    _config = None
