import os
import configparser
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pydantic import  Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings
from pydantic import BaseModel





class API_KEYS(BaseModel):
    OPENAI: Optional[SecretStr]
    DISCORD: Optional[SecretStr]
    ROBOFLOW: Optional[SecretStr]


class DIR_PATHS(BaseModel):
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


class DATALAKE(BaseModel):
    ROOT: str
    GCP_CREDS_PATH: str
    GCP_BUCKET_NAME: str
    HF_TOKEN: str
    HF_DEFAULT_ORG: str
    CHECK_LEGACY_VERSIONS: bool


class DIR_MODELS(BaseModel):
    SAM: str
    YOLO8: str
    YOLO10: str
    DINOV2: str


class FILE_PATHS(BaseModel):
    LOGS: str
    UNITTEST_LOGS: str


class DEFAULT_HOST_URLS(BaseModel):
    SERVERBASE: HttpUrl
    NODE_MANAGER: HttpUrl
    CLUSTER_MANAGER: HttpUrl
    RESERVED_TEST_URL: HttpUrl


class REDIS(BaseModel):
    HOST: str
    PORT: int
    DB: int
    USERNAME: str
    PASSWORD: Optional[SecretStr]



class RABBITMQ(BaseModel):
    HOST: str
    PORT: int
    USER: str
    PASSWORD: Optional[SecretStr]
    DEFAULT_EXCHANGE: str
    DEFAULT_QUEUE: str
    DEFAULT_ROUTING_KEY: str


class LOGGER(BaseModel):
    LOKI_URL: HttpUrl
    LOG_DIR: str


class DIR_SOURCE(BaseModel):
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

    model_config = {
        "env_nested_delimiter": "__",
    }

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
            init_settings,        # constructor kwargs
            env_settings,         # env vars take precedence
            dotenv_settings,      # then .env
            load_ini_settings,    # then INI file (lowest precedence)
            file_secret_settings,
        )


        
        
    

class Config(dict):
    """
    Lightweight configuration wrapper for Mindtrace components.

    This class behaves like a dictionary but initializes itself with default values
    derived from `CoreSettings`, and optionally updates them with user-provided overrides.

    It accepts:
    - A list of `dict`s that override parts of the config.
    - Or a `CoreSettings` instance directly.

    Args:
        extra_settings (Union[List[Dict], CoreSettings], optional): 
            Either a list of dictionaries to override values, or a CoreSettings instance.

    Example:
        .. code-block:: python

            # Override via dict
            config = Config(extra_settings=[{"LOGGER": {"LOG_DIR": "/tmp"}}])

            # Override via full settings object
            custom_settings = CoreSettings(RABBITMQ={"PASSWORD": "env_secret"})
            config = Config(extra_settings=custom_settings)
        
        print(config["LOGGER"]["LOG_DIR"])  # /tmp or from env

    See also:
        - `CoreSettings` for the definition of default configuration schema.
    """

    def __init__(self, extra_settings: Union[List[Dict], CoreSettings, None] = None):
        if isinstance(extra_settings, CoreSettings):
            default_config = extra_settings.model_dump()
        else:
            default_config = CoreSettings().model_dump()
            extra_settings = extra_settings or []

            for override in extra_settings:
                if isinstance(override, (BaseSettings, BaseModel)):
                    override_dict = override.model_dump()
                    default_config = self._deep_update(default_config, override_dict)
                elif isinstance(override, dict):
                    default_config = self._deep_update(default_config, override)

        super().__init__(default_config)

    def _deep_update(self, base: dict, override: dict) -> dict:
        """
        Recursively update nested dictionaries.
        """
        for k, v in override.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                base[k] = self._deep_update(base.get(k, {}), v)
            else:
                base[k] = v
        return base