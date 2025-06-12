import os
import configparser
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import  Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings




class API_KEYS(BaseSettings):
    OPENAI: Optional[SecretStr]
    DISCORD: Optional[SecretStr]
    ROBOFLOW: Optional[SecretStr]


class DIR_PATHS(BaseSettings):
    ROOT: str 
    DATA: str
    MODELS: str
    MODEL_REGISTRY: str
    MINIO_DATA: str
    FILES: str
    LIB: str
    LOGS: str
    TEMP: str
    TESTS: str
    CHECKPOINTS: str
    SERVER_PIDS: str
    RESULTS: str


class DATALAKE(BaseSettings):
    ROOT: str
    GCP_CREDS_PATH: str
    GCP_BUCKET_NAME: str
    HF_TOKEN: str
    HF_DEFAULT_ORG: str
    CHECK_LEGACY_VERSIONS: bool


class DIR_MODELS(BaseSettings):
    SAM: str
    YOLO8: str
    YOLO10: str
    DINOV2: str


class FILE_PATHS(BaseSettings):
    LOGS: str
    UNITTEST_LOGS: str


class DEFAULT_HOST_URLS(BaseSettings):
    SERVERBASE: HttpUrl
    NODE_MANAGER: HttpUrl
    CLUSTER_MANAGER: HttpUrl
    RESERVED_TEST_URL: HttpUrl


class REDIS(BaseSettings):
    HOST: str
    PORT: int
    DB: int
    USERNAME: str
    PASSWORD: Optional[SecretStr]



class RABBITMQ(BaseSettings):
    HOST: str
    PORT: int
    USER: str
    PASSWORD: Optional[SecretStr]
    DEFAULT_EXCHANGE: str
    DEFAULT_QUEUE: str
    DEFAULT_ROUTING_KEY: str


class LOGGER(BaseSettings):
    LOKI_URL: HttpUrl
    LOG_DIR: str


class DIR_SOURCE(BaseSettings):
    ROOT: str



def load_ini_as_dict(ini_path: Path) -> Dict[str, Any]:
    """
    Load and parse an INI file into a nested dictionary with normalized keys.

    Sections and keys are converted to uppercase for uniform access. Tilde (`~`)
    in values is expanded to the user home directory.

    Args:
        ini_path (Path): Path to the `.ini` configuration file.

    Returns:
        Dict[str, Any]: A dictionary where each section is a key mapped to another
        dictionary of key-value pairs from that section.

    Example:
        .. code-block:: ini

            [logging]
            log_dir = ~/logs

        .. code-block:: python

            config = load_ini_as_dict(Path("config.ini"))
            print(config["LOGGING"]["LOG_DIR"])
    """
    if not ini_path.exists():
        return {}

    config = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
    config.optionxform = str
    config.read(ini_path)

    result = {}
    for section in config.sections():
        result[section.upper()] = {
            key.upper(): value.replace("~", os.path.expanduser("~")) if value.startswith("~") else value for key, value in config[section].items()
        }
    return result


def load_ini_settings() -> Dict[str, Any]:
    ini_path = Path(__file__).parent / "config.ini"
    return load_ini_as_dict(ini_path)

class CoreSettings(BaseSettings):
    API_KEYS: API_KEYS
    DIR_PATHS: DIR_PATHS
    DATALAKE: DATALAKE
    DIR_MODELS: DIR_MODELS
    FILE_PATHS: FILE_PATHS
    DEFAULT_HOST_URLS: DEFAULT_HOST_URLS
    REDIS: REDIS
    RABBITMQ: RABBITMQ
    LOGGER: LOGGER
    DIR_SOURCE: DIR_SOURCE

    class Config:
        env_nested_delimiter = "__"

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
            env_settings,         # env vars take precedence
            dotenv_settings,      # then .env
            init_settings,        # then constructor kwargs
            load_ini_settings,    # then INI file (lowest precedence)
            file_secret_settings,
        )


        
        
    

class Config(dict):
    """
    Lightweight configuration wrapper for Mindtrace components.

    This class behaves like a dictionary but initializes itself with default values
    derived from `CoreSettings`, and optionally updates them with user-provided overrides.

    It is typically used to provide structured, overrideable settings across services,
    components, and utilities within the Mindtrace system.

    Args:
        extra_settings: A dictionary of user-defined settings
            that override the defaults from `CoreSettings`.

    Example:
        .. code-block:: python

            config = Config(extra_settings={"log_level": "INFO"})
            print(config["log_level"])  # INFO

    See also:
        - `CoreSettings` for the definition of default configuration schema.
    """
    
    def __init__(self, extra_settings: list[dict] = None):
        default_config = CoreSettings().model_dump()
        for override_dict in extra_settings:
            if override_dict:
                default_config.update(override_dict)
        super().__init__(default_config)

    