from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, SecretStr, field_serializer, model_validator
from pydantic_settings import BaseSettings

from mindtrace.core.utils import expand_tilde_str, load_ini_as_dict


class ConfigModel(BaseModel):
    """Base for config section models. Supports dict-style access."""

    def __getitem__(self, key: str):
        return getattr(self, key)

    def __setitem__(self, key: str, value: Any):
        setattr(self, key, value)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    @field_serializer("*", when_used="json")
    def _reveal_secrets(self, v):
        if isinstance(v, SecretStr):
            return v.get_secret_value()
        return v

    @model_validator(mode="after")
    def _expand_tildes(self):
        for name in self.__class__.model_fields:
            val = getattr(self, name)
            if isinstance(val, str) and "~" in val:
                object.__setattr__(self, name, expand_tilde_str(val))
        return self


class MINDTRACE_API_KEYS(ConfigModel):
    OPENAI: Optional[SecretStr]
    DISCORD: Optional[SecretStr]
    ROBOFLOW: Optional[SecretStr]


class MINDTRACE_TESTING_API_KEYS(ConfigModel):
    DISCORD: Optional[SecretStr]


class MINDTRACE_DIR_PATHS(ConfigModel):
    ROOT: str
    TEMP_DIR: str
    REGISTRY_DIR: str
    STORE_DIR: str = "~/.cache/mindtrace/store"
    LOGGER_DIR: str
    STRUCT_LOGGER_DIR: str
    CLUSTER_REGISTRY_DIR: str
    SERVER_PIDS_DIR: str
    ORCHESTRATOR_LOCAL_CLIENT_DIR: str


class MINDTRACE_LOGGER(ConfigModel):
    USE_STRUCTLOG: bool


class MINDTRACE_DEFAULT_HOST_URLS(ConfigModel):
    SERVICE: str
    CLUSTER_MANAGER: str


class MINDTRACE_MINIO(ConfigModel):
    MINIO_REGISTRY_URI: str
    MINIO_ENDPOINT: str
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: SecretStr


class MINDTRACE_CLUSTER(ConfigModel):
    DEFAULT_REDIS_URL: str
    MINIO_REGISTRY_URI: str
    MINIO_HOST: str
    MINIO_PORT: int
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: SecretStr
    MINIO_BUCKET: str
    RABBITMQ_HOST: str
    RABBITMQ_PORT: int
    RABBITMQ_USERNAME: str
    RABBITMQ_PASSWORD: SecretStr
    WORKER_PORTS_RANGE: str


class MINDTRACE_MCP(ConfigModel):
    MOUNT_PATH: str
    HTTP_APP_PATH: str


class MINDTRACE_WORKER(ConfigModel):
    DEFAULT_REDIS_URL: str


class MINDTRACE_GCP(ConfigModel):
    GCP_PROJECT_ID: str
    GCP_BUCKET_NAME: str
    GCP_CREDENTIALS_PATH: str
    GCP_LOCATION: str
    GCP_STORAGE_CLASS: str


class MINDTRACE_GCP_REGISTRY(ConfigModel):
    GCP_REGISTRY_URI: str
    GCP_BUCKET_NAME: str


def load_ini_settings() -> dict[str, Any]:
    ini_path = Path(__file__).parent / "config.ini"
    return load_ini_as_dict(ini_path)


class Config(BaseSettings, ConfigModel):
    """Central configuration for Mindtrace components.

    Loads from (highest to lowest precedence):
        1. Constructor kwargs
        2. Environment variables (``SECTION__KEY`` delimiter)
        3. ``.env`` file
        4. ``config.ini`` bundled with the package

    Supports dict-style access (``settings["SECTION"]["KEY"]``) and
    secret retrieval (``settings.get_secret("SECTION", "KEY")``).
    """

    MINDTRACE_API_KEYS: MINDTRACE_API_KEYS
    MINDTRACE_TESTING_API_KEYS: MINDTRACE_TESTING_API_KEYS
    MINDTRACE_DIR_PATHS: MINDTRACE_DIR_PATHS
    MINDTRACE_DEFAULT_HOST_URLS: MINDTRACE_DEFAULT_HOST_URLS
    MINDTRACE_MINIO: MINDTRACE_MINIO
    MINDTRACE_GCP: MINDTRACE_GCP
    MINDTRACE_GCP_REGISTRY: MINDTRACE_GCP_REGISTRY
    MINDTRACE_CLUSTER: MINDTRACE_CLUSTER
    MINDTRACE_MCP: MINDTRACE_MCP
    MINDTRACE_WORKER: MINDTRACE_WORKER
    MINDTRACE_TEST_PARAM: str = ""
    MINDTRACE_LOGGER: MINDTRACE_LOGGER

    model_config = {
        "env_nested_delimiter": "__",
        "extra": "allow",
    }

    def __init__(self, _settings: dict | None = None, /, **kwargs):
        if _settings is not None:
            kwargs = {**_settings, **kwargs}
        super().__init__(**kwargs)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        dotenv_settings,
        env_settings,
        file_secret_settings,
    ):
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            load_ini_settings,
            file_secret_settings,
        )

    def get_secret(self, *path: str) -> str | None:
        """Retrieve a secret value by path components.

        Args:
            *path: Path components (e.g., ``"MINDTRACE_API_KEYS"``, ``"OPENAI"``).

        Returns:
            The unmasked secret value, or ``None`` if not found.

        Example::

            settings = Config()
            key = settings.get_secret("MINDTRACE_API_KEYS", "OPENAI")
        """
        obj: Any = self
        for key in path:
            obj = getattr(obj, key, None)
            if obj is None:
                return None
        if isinstance(obj, SecretStr):
            return obj.get_secret_value()
        return str(obj) if obj is not None else None
