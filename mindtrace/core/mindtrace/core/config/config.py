import os
import configparser
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Callable, Tuple, get_origin, get_args
from copy import deepcopy

from pydantic import  Field, HttpUrl, SecretStr, AnyUrl
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


# Union alias used across core for configuration overrides and settings
SettingsLike = Union[
    Dict[str, Any],
    List[Union[Dict[str, Any], BaseSettings, BaseModel]],
    CoreSettings,
    BaseSettings,
    BaseModel,
    None,
]


class Config(dict):
    """
    Lightweight configuration wrapper for Mindtrace components.

    This class behaves like a dictionary but initializes itself with default values
    derived from `CoreSettings`, and optionally updates them with user-provided overrides.

    It accepts:
    - A list of `dict`s/BaseSettings/BaseModel that override parts of the config.
    - Or a `CoreSettings`/BaseSettings/BaseModel instance directly.

    Args:
        extra_settings (SettingsLike, optional): Override values or full settings object.
    """

    def __init__(self, extra_settings: SettingsLike = None):
        # Track secret field paths and store real secret values
        self._secret_paths: set[Tuple[str, ...]] = set()
        self._secrets: Dict[Tuple[str, ...], str] = {}

        # Base defaults
        if isinstance(extra_settings, CoreSettings):
            default_config = extra_settings.model_dump()
            self._secret_paths.update(self._collect_secret_paths_from_model(type(extra_settings)))
            extra_list: List[Dict[str, Any]] = []
        else:
            default_config = CoreSettings().model_dump() #loads values in resolution order , dumps a dictionary representation of the CoreSettings object
            self._secret_paths.update(self._collect_secret_paths_from_model(CoreSettings))
            # Normalize overrides into a list of dicts
            if extra_settings is None:
                extra_list = []
            elif isinstance(extra_settings, list):
                extra_list = []
                for item in extra_settings:
                    if isinstance(item, (BaseSettings, BaseModel)):
                        self._secret_paths.update(self._collect_secret_paths_from_model(type(item)))
                        extra_list.append(item.model_dump())
                    elif isinstance(item, dict):
                        extra_list.append(item)
            elif isinstance(extra_settings, (BaseSettings, BaseModel)):
                self._secret_paths.update(self._collect_secret_paths_from_model(type(extra_settings)))
                extra_list = [extra_settings.model_dump()]
            elif isinstance(extra_settings, dict):
                extra_list = [extra_settings]
            else:
                extra_list = []

        for override in extra_list:
            default_config = self._deep_update(default_config, override)

        # Overlay environment variables last so they can override dict/BaseModel overrides
        default_config = self._apply_env_overrides(default_config)

        # Coerce everything to string and mask secrets by default
        default_config = self._stringify_and_mask(default_config)

        super().__init__(default_config)

    @classmethod
    def load(
        cls,
        *,
        defaults: Optional[CoreSettings] = None,
        overrides: Optional[Union[Dict[str, Any], List[Union[Dict[str, Any], BaseSettings, BaseModel]], BaseSettings, BaseModel]] = None,
        file_loader: Optional[Callable[[], Dict[str, Any]]] = None,
    ) -> "Config":
        """Create a Config from defaults, optional file loader, and runtime overrides."""
        base = (defaults or CoreSettings()).model_dump()
        if file_loader is not None:
            loaded = file_loader() or {}
            base = cls._deep_update_dict(base, loaded)
        if overrides is not None:
            items: List[Dict[str, Any]] = []
            if isinstance(overrides, (BaseSettings, BaseModel)):
                items = [overrides.model_dump()]
            elif isinstance(overrides, dict):
                items = [overrides]
            elif isinstance(overrides, list):
                for o in overrides:
                    if isinstance(o, (BaseSettings, BaseModel)):
                        items.append(o.model_dump())
                    elif isinstance(o, dict):
                        items.append(o)
            for o in items:
                base = cls._deep_update_dict(base, o)
        # Overlay env and return through __init__ pipeline (which masks)
        base = cls._apply_env_overrides_static(base)
        return cls([base])

    def clone_with_overrides(self, *overrides: SettingsLike) -> "Config":
        """Return a new Config clone with overrides applied (original remains unchanged)."""
        items: List[Dict[str, Any]] = [deepcopy(dict(self))]
        def push(x):
            if isinstance(x, (BaseSettings, BaseModel)):
                items.append(x.model_dump())
            elif isinstance(x, CoreSettings):
                items.append(x.model_dump())
            elif isinstance(x, dict):
                items.append(x)
            elif isinstance(x, list):
                for y in x: push(y)
            elif x is None:
                pass
        for o in overrides:
            push(o)
        return Config(items)

    def get_secret(self, *path: str) -> Optional[str]:
        """Retrieve a secret by dotted path components, e.g., get_secret("API_KEYS", "OPENAI")."""
        return self._secrets.get(tuple(path))

    def secret_paths(self) -> List[str]:
        """Return dotted paths of fields considered secrets."""
        return sorted([".".join(p) for p in self._secret_paths])

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

    @staticmethod
    def _deep_update_dict(base: dict, override: dict) -> dict:
        for k, v in (override or {}).items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                base[k] = Config._deep_update_dict(base.get(k, {}), v)
            else:
                base[k] = v
        return base

    @staticmethod
    def _apply_env_overrides_static(base: dict, delimiter: str = "__") -> dict:
        result = deepcopy(base)

        def set_nested(target: dict, path: List[str], value: Any):
            node = target
            for key in path[:-1]:
                if key not in node or not isinstance(node[key], dict):
                    node[key] = {}
                node = node[key]
            node[path[-1]] = Config._coerce_env_value(value)

        for env_key, env_value in os.environ.items():
            if delimiter not in env_key:
                continue
            parts = [p.strip().upper() for p in env_key.split(delimiter) if p.strip()]
            if not parts:
                continue
            set_nested(result, parts, env_value)

        return result

    def _apply_env_overrides(self, base: dict, delimiter: str = "__") -> dict:
        return Config._apply_env_overrides_static(base, delimiter)

    @staticmethod
    def _coerce_env_value(value: str) -> Any:
        lower = value.lower()
        if lower in {"true", "false"}:
            return lower == "true"
        try:
            if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
                return int(value)
        except Exception:
            pass
        try:
            return float(value)
        except Exception:
            return value

    def _stringify_and_mask(self, data: Dict[str, Any], mask: str = "********") -> Dict[str, Any]:
        def convert(v: Any, path: Tuple[str, ...]) -> str | Dict[str, Any] | List[Any]:
            if isinstance(v, SecretStr):
                val = v.get_secret_value()
                self._secrets[path] = val
                return mask
            if isinstance(v, AnyUrl):
                val = str(v)
                return mask if path in self._secret_paths else val
            if isinstance(v, dict):
                return {k: convert(x, path + (k,)) for k, x in v.items()}
            if isinstance(v, (list, tuple, set)):
                return [convert(x, path) for x in v]
            # Convert to string and mask if marked secret path
            sval = str(v)
            if path in self._secret_paths:
                self._secrets[path] = sval
                return mask
            return sval
        return convert(data, ())  # type: ignore

    @staticmethod
    def _stringify_dict_static(data: Dict[str, Any]) -> Dict[str, Any]:
        def convert(v: Any) -> str | Dict[str, Any] | List[Any]:
            if isinstance(v, SecretStr):
                return v.get_secret_value()
            if isinstance(v, AnyUrl):
                return str(v)
            if isinstance(v, dict):
                return {k: convert(x) for k, x in v.items()}
            if isinstance(v, (list, tuple, set)):
                return [convert(x) for x in v]
            return str(v)
        return convert(data)  # type: ignore

    def _collect_secret_paths_from_model(self, model_cls: type[BaseModel] | type[BaseSettings], prefix: Tuple[str, ...] = ()) -> set[Tuple[str, ...]]:
        paths: set[Tuple[str, ...]] = set()
        fields = getattr(model_cls, "__pydantic_fields__", {})
        for name, field in fields.items():
            ann = getattr(field, "annotation", None)
            if self._is_secret_annotation(ann):
                paths.add(prefix + (name,))
                continue
            # Recurse into nested models
            nested_cls = self._extract_model_class(ann)
            if nested_cls is not None:
                paths.update(self._collect_secret_paths_from_model(nested_cls, prefix + (name,)))
        return paths

    def _is_secret_annotation(self, ann: Any) -> bool:
        if ann is None:
            return False
        if ann is SecretStr:
            return True
        origin = get_origin(ann)
        if origin is Union:
            return any(a is SecretStr for a in get_args(ann))
        return False

    def _extract_model_class(self, ann: Any) -> Optional[type]:
        try:
            if isinstance(ann, type) and (issubclass(ann, BaseModel) or issubclass(ann, BaseSettings)):
                return ann
        except TypeError:
            pass
        origin = get_origin(ann)
        if origin is Union:
            for a in get_args(ann):
                try:
                    if isinstance(a, type) and (issubclass(a, BaseModel) or issubclass(a, BaseSettings)):
                        return a
                except TypeError:
                    continue
        return None