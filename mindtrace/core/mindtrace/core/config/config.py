import os
import configparser
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Callable, Tuple, get_origin, get_args
from copy import deepcopy

from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings
from pydantic import AnyUrl





class MINDTRACE_API_KEYS(BaseModel):
    OPENAI: Optional[SecretStr]
    DISCORD: Optional[SecretStr]
    ROBOFLOW: Optional[SecretStr]


class MINDTRACE_DIR_PATHS(BaseModel):
    ROOT: str
    TEMP_DIR: str
    REGISTRY_DIR: str
    LOGGER_DIR: str
    CLUSTER_REGISTRY_DIR: str
    SERVER_PIDS_DIR: str


class MINDTRACE_DEFAULT_HOST_URLS(BaseModel):
    SERVICE: str
    CLUSTER_MANAGER: str


class MINDTRACE_MINIO(BaseModel):
    MINIO_REGISTRY_URI: str
    MINIO_ENDPOINT: str
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: SecretStr


class MINDTRACE_CLUSTER(BaseModel):
    DEFAULT_REDIS_URL: str
    MINIO_ENDPOINT: str
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: SecretStr
    MINIO_BUCKET: str

class MINDTRACE_MCP(BaseModel):
    MOUNT_PATH: str
    HTTP_APP_PATH: str


class MINDTRACE_WORKER(BaseModel):
    DEFAULT_REDIS_URL: str



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
    MINDTRACE_API_KEYS: MINDTRACE_API_KEYS
    MINDTRACE_DIR_PATHS: MINDTRACE_DIR_PATHS
    MINDTRACE_DEFAULT_HOST_URLS: MINDTRACE_DEFAULT_HOST_URLS
    MINDTRACE_MINIO: MINDTRACE_MINIO
    MINDTRACE_CLUSTER: MINDTRACE_CLUSTER
    MINDTRACE_MCP: MINDTRACE_MCP
    MINDTRACE_WORKER: MINDTRACE_WORKER
    MINDTRACE_TEST_PARAM: str = ""

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
        def _expand_tilde(obj):
            if isinstance(obj, str):
                return os.path.expanduser(obj) if obj.startswith("~") else obj
            if isinstance(obj, dict):
                return {k: _expand_tilde(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple, set)):
                t = type(obj)
                return t(_expand_tilde(v) for v in obj)
            return obj

        def env_settings_expanded():
            data = env_settings()
            return _expand_tilde(data)

        return (
            init_settings,           # constructor kwargs
            env_settings_expanded,   # env vars (with '~' expanded) take precedence
            dotenv_settings,         # then .env
            load_ini_settings,       # then INI file (lowest precedence)
            file_secret_settings,
        )


# Union alias used across core for configuration overrides and settings
SettingsLike = Union[
    Dict[str, Any],
    List[Union[Dict[str, Any], BaseSettings, BaseModel]],
    BaseSettings,
    BaseModel,
    None,
]


class _AttrView:
    """
    Lightweight attribute-access wrapper around a mapping.

    Enables access like obj.SECTION.KEY for nested dictionaries.
    """

    def __init__(self, data: Dict[str, Any]):
        self._data = data

    def __getattr__(self, name: str):
        if name in self._data:
            value = self._data[name]
            if isinstance(value, dict):
                return _AttrView(value)
            if isinstance(value, list):
                return [(_AttrView(v) if isinstance(v, dict) else v) for v in value]
            return value
        raise AttributeError(f"No such attribute: {name}")

    def __getitem__(self, key: str):
        value = self._data[key]
        if isinstance(value, dict):
            return _AttrView(value)
        if isinstance(value, list):
            return [(_AttrView(v) if isinstance(v, dict) else v) for v in value]
        return value

    def __repr__(self) -> str:
        return f"_AttrView({self._data!r})"


class Config(dict):
    """
    Unified configuration manager for Mindtrace components.

    The `Config` class consolidates configuration from sources including
    dictionaries, Pydantic `BaseSettings` or `BaseModel` objects. 
    It supports user provided arguments and environment variable overrides, path normalization by expanding the `~` character.

    Key Features:
    -------------
    - Accepts multiple configuration formats: `dict`, `BaseModel`, `BaseSettings`, or lists of these.
    - Attr-style and dict-style access to nested keys.
    - Supports secret fields using `pydantic.SecretStr`, preserving masking them by default.
    - Overlays environment variables (`ENV_VAR__NESTED_KEY`) over default configs.
    - Provides cloning, JSON export, and dynamic override capabilities.

    Args:
        extra_settings: Configuration overrides or full config objects.
            Can be a `dict`, `BaseSettings`, `BaseModel`, or list of any of these.

    Example:
        >>> from mindtrace.core.config import Config, CoreSettings
        >>> config = Config(CoreSettings())  # Load from BaseSettings
        >>> print(config["MINDTRACE_API_KEYS"]["OPENAI"])  # Masked by default
        >>> config.get_secret("MINDTRACE_API_KEYS", "OPENAI")  # Real secret value
    """

    def __init__(self, extra_settings: SettingsLike = None, *, apply_env: bool = True):
        # Track secret field paths and store real secret values
        self._secret_paths: set[Tuple[str, ...]] = set()
        self._secrets: Dict[Tuple[str, ...], str] = {}

        # Start from empty baseline; no implicit CoreSettings defaults
        default_config: Dict[str, Any] = {}

        # Normalize extras and collect secret paths from typed models
        extra_list: List[Dict[str, Any]] = []
        if extra_settings is None:
            extra_list = []
        elif isinstance(extra_settings, list):
            converted: List[Dict[str, Any]] = []
            for item in extra_settings:
                if isinstance(item, (BaseSettings, BaseModel)):
                    self._secret_paths.update(self._collect_secret_paths_from_model(type(item)))
                    converted.append(item.model_dump())
                elif isinstance(item, dict):
                    converted.append(item)
            extra_list = converted
        elif isinstance(extra_settings, (BaseSettings, BaseModel)):
            self._secret_paths.update(self._collect_secret_paths_from_model(type(extra_settings)))
            extra_list = [extra_settings.model_dump()]
        elif isinstance(extra_settings, dict):
            extra_list = [extra_settings]

        for override in extra_list:
            default_config = self._deep_update(default_config, override)

        # Overlay environment variables last so they can override provided settings
        if apply_env:
            default_config = self._apply_env_overrides(default_config)

        # Coerce everything to string and mask secrets by default
        default_config = self._stringify_and_mask(default_config)

        super().__init__(default_config)

    def __getattr__(self, name: str):
        """Enable attribute-style access for top-level keys."""
        if name in self:
            value = self[name]
            if isinstance(value, dict):
                return _AttrView(value)
            if isinstance(value, list):
                return [(_AttrView(v) if isinstance(v, dict) else v) for v in value]
            return value
        raise AttributeError(f"No such attribute: {name}")

    @classmethod
    def load(
        cls,
        *,
        defaults: Optional[Union[Dict[str, Any], BaseSettings, BaseModel]] = None,
        overrides: Optional[Union[Dict[str, Any], List[Union[Dict[str, Any], BaseSettings, BaseModel]], BaseSettings, BaseModel]] = None,
        file_loader: Optional[Callable[[], Dict[str, Any]]] = None,
    ) -> "Config":
        """Create a Config from optional defaults, optional file loader, and runtime overrides.
        """
        base: Dict[str, Any] = {}
        if isinstance(defaults, (BaseSettings, BaseModel)):
            base = defaults.model_dump()
        elif isinstance(defaults, dict):
            base = defaults
        if file_loader is not None:
            loaded = file_loader() or {}
            base = cls._deep_update_dict(base, loaded)
        # Apply environment variables before runtime overrides
        base = cls._apply_env_overrides_static(base)
        # Apply overrides last so they have highest precedence
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
        # Prevent __init__ from re-applying env so overrides remain highest
        return cls([base], apply_env=False)

    @classmethod
    def load_json(cls, path: str | Path) -> "Config":
        """Load from a JSON file (acts as file_loader layer) and apply env + masking."""
        def _loader() -> Dict[str, Any]:
            with open(path, "r") as f:
                return json.load(f)
        return cls.load(file_loader=_loader)

    def save_json(self, path: str | Path, *, reveal_secrets: bool = False, indent: int = 4) -> None:
        """Save to JSON; masked by default. Set reveal_secrets=True to write real secrets."""
        data = self.to_revealed_strings() if reveal_secrets else deepcopy(dict(self))
        with open(path, "w") as f:
            json.dump(data, f, indent=indent)

    def clone_with_overrides(self, *overrides: SettingsLike) -> "Config":
        """Return a new Config clone with overrides applied (original remains unchanged)."""
        items: List[Dict[str, Any]] = [deepcopy(dict(self))]
        def push(x):
            if isinstance(x, (BaseSettings, BaseModel)):
                items.append(x.model_dump())
            elif isinstance(x, dict):
                items.append(x)
            elif isinstance(x, list):
                for y in x: push(y)
            elif x is None:
                pass
        for o in overrides:
            push(o)
        return Config(items, apply_env=False)

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
            # Convert to string; expand '~' for non-secret paths
            original_sval = str(v)
            if path in self._secret_paths:
                self._secrets[path] = original_sval
                return mask
            expanded = os.path.expanduser(original_sval) if original_sval.startswith("~") else original_sval
            return expanded
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
            s = str(v)
            return os.path.expanduser(s) if s.startswith("~") else s
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



class CoreConfig(Config):
    """
    Wrapper around `Config` that always includes `CoreSettings` by default.

    Usage:
        from mindtrace.core.config import CoreConfig
        cfg = CoreConfig()  # loads CoreSettings (env + .env + INI with '~' expansion)

    You can still pass extra overrides; they are applied on top of CoreSettings
    and remain highest precedence. Env is not re-applied at the Config layer.
    """

    def __init__(self, extra_settings: SettingsLike = None):
        if extra_settings is None:
            extras: List[Any] = [CoreSettings()]
        elif isinstance(extra_settings, list):
            extras = [CoreSettings()] + extra_settings
        else:
            extras = [CoreSettings(), extra_settings]
        # Do not re-apply env here; CoreSettings already applied env and
        # we want provided overrides to remain highest precedence
        super().__init__(extra_settings=extras, apply_env=False)