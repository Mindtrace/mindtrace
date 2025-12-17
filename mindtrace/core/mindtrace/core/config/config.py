import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union, get_args, get_origin

from pydantic import AnyUrl, BaseModel, SecretStr
from pydantic_settings import BaseSettings

from mindtrace.core.utils import expand_tilde, expand_tilde_str, load_ini_as_dict


class MINDTRACE_API_KEYS(BaseModel):
    OPENAI: Optional[SecretStr]
    DISCORD: Optional[SecretStr]
    ROBOFLOW: Optional[SecretStr]


class MINDTRACE_TESTING_API_KEYS(BaseModel):
    DISCORD: Optional[SecretStr]


class MINDTRACE_DIR_PATHS(BaseModel):
    ROOT: str
    TEMP_DIR: str
    REGISTRY_DIR: str
    LOGGER_DIR: str
    STRUCT_LOGGER_DIR: str
    CLUSTER_REGISTRY_DIR: str
    SERVER_PIDS_DIR: str
    ORCHESTRATOR_LOCAL_CLIENT_DIR: str


class MINDTRACE_LOGGER(BaseModel):
    USE_STRUCTLOG: bool


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
    MINIO_REGISTRY_URI: str
    MINIO_ENDPOINT: str
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: SecretStr
    MINIO_BUCKET: str
    RABBITMQ_HOST: str
    RABBITMQ_PORT: int
    RABBITMQ_USERNAME: str
    RABBITMQ_PASSWORD: str
    WORKER_PORTS_RANGE: str


class MINDTRACE_MCP(BaseModel):
    MOUNT_PATH: str
    HTTP_APP_PATH: str


class MINDTRACE_WORKER(BaseModel):
    DEFAULT_REDIS_URL: str


class MINDTRACE_GCP(BaseModel):
    GCP_REGISTRY_URI: str
    GCP_PROJECT_ID: str
    GCP_BUCKET_NAME: str
    GCP_CREDENTIALS_PATH: str
    GCP_LOCATION: str
    GCP_STORAGE_CLASS: str


def load_ini_settings() -> Dict[str, Any]:
    ini_path = Path(__file__).parent / "config.ini"
    return load_ini_as_dict(ini_path)


class CoreSettings(BaseSettings):
    MINDTRACE_API_KEYS: MINDTRACE_API_KEYS
    MINDTRACE_TESTING_API_KEYS: MINDTRACE_TESTING_API_KEYS
    MINDTRACE_DIR_PATHS: MINDTRACE_DIR_PATHS
    MINDTRACE_DEFAULT_HOST_URLS: MINDTRACE_DEFAULT_HOST_URLS
    MINDTRACE_MINIO: MINDTRACE_MINIO
    MINDTRACE_GCP: MINDTRACE_GCP
    MINDTRACE_CLUSTER: MINDTRACE_CLUSTER
    MINDTRACE_MCP: MINDTRACE_MCP
    MINDTRACE_WORKER: MINDTRACE_WORKER
    MINDTRACE_TEST_PARAM: str = ""
    MINDTRACE_LOGGER: MINDTRACE_LOGGER

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
        def env_settings_expanded():
            data = env_settings()
            return expand_tilde(data)

        return (
            init_settings,  # constructor kwargs
            env_settings_expanded,  # env vars (with '~' expanded) take precedence
            dotenv_settings,  # then .env
            load_ini_settings,  # then INI file (lowest precedence)
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
    """Unified configuration manager for Mindtrace components.

    The `Config` class consolidates configuration from sources including
    dictionaries, Pydantic `BaseSettings` or `BaseModel` objects.
    It supports user provided arguments and environment variable overrides, path normalization by expanding the `~` character.

    Key Features:

    - Accepts multiple configuration formats: `dict`, `BaseModel`, `BaseSettings`, or lists of these.
    - Attr-style and dict-style access to nested keys.
    - Supports secret fields using `pydantic.SecretStr`, preserving masking them by default.
    - Overlays environment variables (`ENV_VAR__NESTED_KEY`) over default configs.
    - Provides cloning, JSON export, and dynamic override capabilities.

    Args:
        extra_settings: Configuration overrides or full config objects.
            Can be a `dict`, `BaseSettings`, `BaseModel`, or list of any of these.
        apply_env_overrides: Whether to apply environment variable overrides.
            If True, environment variables will be applied over the default configs.
            If False, environment variables will not be applied.

    Examples:
        Basic usage with CoreSettings:
        ```python
        from mindtrace.core.config import Config, CoreSettings
        config = Config(CoreSettings())
        print(config["MINDTRACE_API_KEYS"]["OPENAI"])  # ******** (masked)
        print(config.get_secret("MINDTRACE_API_KEYS", "OPENAI"))  # Real secret value
        ```

        Load from INI file with overrides:
        ```python
        from pathlib import Path
        from mindtrace.core.config import Config
        from mindtrace.core.utils import load_ini_as_dict

        def my_loader():
            file_path = Path("sample.ini")
            return load_ini_as_dict(file_path)

        defaults = my_loader()
        overrides = {
            "MINDTRACE_DIR_PATHS": {
                "TEMP_DIR": "/tmp/logs",
                "REGISTRY_DIR": "/tmp/registry"
            }
        }
        config = Config.load(defaults=defaults, overrides=overrides)
        ```

        Access values in multiple ways:
        ```python
        # Attribute style access
        print(config.MINDTRACE_DIR_PATHS.TEMP_DIR)

        # Dict style access
        print(config["MINDTRACE_DIR_PATHS"]["TEMP_DIR"])

        # Get method
        print(config.get("MINDTRACE_DIR_PATHS").get("TEMP_DIR"))
        ```

        Save and reload configuration:
        ```python
        # Save config to JSON
        config.save_json("saved_config.json")

        # Load config back
        reloaded = Config.load_json("saved_config.json")
        ```

        Clone config with overrides (original unchanged):
        ```python
        cloned = config.clone_with_overrides({
            "MINDTRACE_DIR_PATHS": {
                "TEMP_DIR": "/tmp/clone/logs"
            }
        })
        print("Original:", config.MINDTRACE_DIR_PATHS.TEMP_DIR)  # Unchanged
        print("Cloned:", cloned.MINDTRACE_DIR_PATHS.TEMP_DIR)   # New value
        ```

        Working with secret fields:
        ```python
        from pydantic import BaseModel, SecretStr
        from mindtrace.core.config import Config

        class APIKeys(BaseModel):
            OPENAI: SecretStr
            DISCORD: SecretStr

        class AppSettings(BaseModel):
            API_KEYS: APIKeys

        config = Config(AppSettings(API_KEYS=APIKeys(
            OPENAI=SecretStr("sk-abc123"),
            DISCORD=SecretStr("discord-token")
        )))

        # Access masked values
        print(config.API_KEYS.OPENAI)           # ********
        print(config.API_KEYS.DISCORD)          # ********

        # Get real secret values
        print(config.get_secret("API_KEYS", "OPENAI"))   # sk-abc123
        print(config.get_secret("API_KEYS", "DISCORD"))  # discord-token
        ```
    """

    def __init__(self, extra_settings: SettingsLike = None, *, apply_env_overrides: bool = True):
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

        # Only apply environment variable overrides if we have some base configuration
        # or if explicitly requested. This prevents empty Config() from picking up random env vars.
        # Check if any of the provided settings actually contain data
        has_any_data = any(len(item) > 0 for item in extra_list) if extra_list else False
        if apply_env_overrides and (has_any_data or len(default_config) > 0):
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
        overrides: Optional[
            Union[Dict[str, Any], List[Union[Dict[str, Any], BaseSettings, BaseModel]], BaseSettings, BaseModel]
        ] = None,
        file_loader: Optional[Callable[[], Dict[str, Any]]] = None,
    ) -> "Config":
        """Create a Config from optional defaults, optional file loader, and runtime overrides.

        This is the recommended way to create a Config instance with proper precedence order:
        1. File loader (lowest precedence)
        2. Defaults
        3. Environment variables
        4. Runtime overrides (highest precedence)

        Args:
            defaults: Base configuration as dict, BaseSettings, or BaseModel
            overrides: Runtime overrides that take highest precedence
            file_loader: Optional callable that returns a dict (e.g., from INI file)

        Returns:
            Config instance with all sources merged

        Examples:
            Load from INI file with overrides:
            ```python
            from pathlib import Path
            from mindtrace.core.config import Config
            from mindtrace.core.utils import load_ini_as_dict

            def ini_loader():
                return load_ini_as_dict(Path("config.ini"))

            config = Config.load(
                file_loader=ini_loader,
                overrides={"MINDTRACE_DIR_PATHS": {"TEMP_DIR": "/custom/tmp"}}
            )
            ```

            Load with Pydantic model defaults:
            ```python
            from pydantic import BaseModel
            from mindtrace.core.config import Config

            class MySettings(BaseModel):
                API_URL: str = "http://localhost:8000"
                DEBUG: bool = False

            config = Config.load(
                defaults=MySettings(),
                overrides={"DEBUG": True}
            )
            ```
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
        return cls([base], apply_env_overrides=False)

    @classmethod
    def load_json(cls, path: str | Path) -> "Config":
        """Load configuration from a JSON file with environment variable overrides and secret masking.

        This method loads configuration data from a JSON file and applies the same
        processing as the main Config class: environment variable overrides and
        automatic masking of secret fields.

        Args:
            path: Path to the JSON file (string or Path object)

        Returns:
            Config instance loaded from the JSON file

        Examples:
            Load from JSON file:
            ```python
            from mindtrace.core.config import Config

            # Load configuration from JSON file
            config = Config.load_json("config.json")
            print(config.MINDTRACE_DIR_PATHS.TEMP_DIR)
            ```

            Load with environment overrides:
            ```python
            import os
            os.environ["MINDTRACE_DEFAULT_HOST_URLS__SERVICE"] = "http://env-override:8000"

            config = Config.load_json("config.json")
            # Environment variable will override the value from JSON
            print(config.MINDTRACE_DEFAULT_HOST_URLS.SERVICE)  # http://env-override:8000
            ```

        Note:
            The JSON file should contain the same structure as expected by Config.
            Secret fields will be automatically masked when accessed normally.
        """

        def _loader() -> Dict[str, Any]:
            with open(path, "r") as f:
                return json.load(f)

        return cls.load(file_loader=_loader)

    def save_json(self, path: str | Path, *, reveal_secrets: bool = False, indent: int = 4) -> None:
        """Save configuration to a JSON file with optional secret revelation.

        This method serializes the current configuration to a JSON file. By default,
        secret fields are masked (shown as ********) for security. You can optionally
        reveal the actual secret values by setting reveal_secrets=True.

        Args:
            path: Path where to save the JSON file (string or Path object)
            reveal_secrets: If True, writes actual secret values instead of masked ones
            indent: JSON indentation level for pretty printing (default: 4)

        Returns:
            None

        Raises:
            RuntimeError: If file writing or JSON serialization fails

        Examples:
            Save with masked secrets (default):
            ```python
            config = Config(CoreSettings())
            config.save_json("config.json")
            # Secret fields will be saved as "********"
            ```

            Save with revealed secrets:
            ```python
            config.save_json("config.json", reveal_secrets=True)
            # Secret fields will be saved with actual values
            ```

            Save with custom indentation:
            ```python
            config.save_json("config.json", indent=2)
            ```

        Note:
            Parent directories are created automatically if they don't exist.
            Use reveal_secrets=True only when necessary for debugging or migration.
        """
        try:
            p = Path(path)
            # Ensure parent directory exists
            if p.parent and not p.parent.exists():
                p.parent.mkdir(parents=True, exist_ok=True)

            data = self.to_revealed_strings() if reveal_secrets else deepcopy(dict(self))
            # Attempt to serialize to validate JSON-compatibility before writing file
            payload = json.dumps(data, indent=indent)
            with p.open("w") as f:
                f.write(payload)
        except (TypeError, OSError) as e:
            raise RuntimeError(f"Failed to save config to '{path}': {e}") from e

    def to_revealed_strings(self) -> Dict[str, Any]:
        """Convert the config to a dictionary with revealed secret values."""
        result = deepcopy(dict(self))

        def reveal_secrets(data: Dict[str, Any], path: Tuple[str, ...] = ()) -> None:
            for key, value in data.items():
                current_path = path + (key,)
                if current_path in self._secrets:
                    data[key] = self._secrets[current_path]
                elif isinstance(value, dict):
                    reveal_secrets(value, current_path)
                elif isinstance(value, list):
                    for i, item in enumerate(value):
                        if isinstance(item, dict):
                            reveal_secrets(item, current_path + (str(i),))

        reveal_secrets(result)
        return result

    def clone_with_overrides(self, *overrides: SettingsLike) -> "Config":
        """Return a new Config clone with overrides applied (original remains unchanged).

        This method creates a deep copy of the current config and applies the provided
        overrides without modifying the original configuration. Useful for creating
        temporary configurations or testing different settings.

        Args:
            *overrides: Configuration overrides as dict, BaseSettings, BaseModel, or lists of these

        Returns:
            New Config instance with overrides applied

        Examples:
            Clone with simple overrides:
            ```python
            original = Config({"API_URL": "http://prod:8000", "DEBUG": False})
            cloned = original.clone_with_overrides({"DEBUG": True})

            print(original.DEBUG)  # False (unchanged)
            print(cloned.DEBUG)   # True (new value)
            ```

            Clone with nested overrides:
            ```python
            cloned = config.clone_with_overrides({
                "MINDTRACE_DIR_PATHS": {
                    "TEMP_DIR": "/tmp/testing",
                    "REGISTRY_DIR": "/tmp/test_registry"
                }
            })
            ```

            Clone with multiple overrides:
            ```python
            cloned = config.clone_with_overrides(
                {"DEBUG": True},
                {"API_URL": "http://test:8000"},
                {"LOGGING_LEVEL": "DEBUG"}
            )
            ```
        """
        items: List[Dict[str, Any]] = [deepcopy(dict(self))]

        def push(x):
            if isinstance(x, (BaseSettings, BaseModel)):
                items.append(x.model_dump())
            elif isinstance(x, dict):
                items.append(x)
            elif isinstance(x, (list, tuple)):
                # Flatten nested lists/tuples safely
                for y in x:
                    push(y)
            elif x is None:
                # Explicitly ignore Nones
                pass
            else:
                raise TypeError(
                    f"Unsupported override type: {type(x).__name__}. "
                    "Expected dict, BaseSettings, BaseModel, or list/tuple of these."
                )

        for o in overrides:
            push(o)
        return Config(items, apply_env_overrides=False)

    def get_secret(self, *path: str) -> Optional[str]:
        """Retrieve a secret by dotted path components.

        This method accesses the real (unmasked) value of secret fields that were
        defined using pydantic.SecretStr. The secret values are stored internally
        and can be retrieved using this method.

        Args:
            *path: Path components to the secret field (e.g., "API_KEYS", "OPENAI")

        Returns:
            The real secret value as string, or None if not found

        Examples:
            Get OpenAI API key:
            ```python
            config = Config(CoreSettings())
            api_key = config.get_secret("MINDTRACE_API_KEYS", "OPENAI")
            print(api_key)  # "sk-abc123..." (real value)
            ```
            Working with custom secret fields:
            ```python
            from pydantic import BaseModel, SecretStr
            from mindtrace.core.config import Config

            class APIKeys(BaseModel):
                OPENAI: SecretStr
                DISCORD: SecretStr

            config = Config(APIKeys(
                OPENAI=SecretStr("sk-abc123"),
                DISCORD=SecretStr("discord-token")
            ))

            # Access masked value
            print(config.OPENAI)  # ********

            # Get real value
            print(config.get_secret("OPENAI"))  # sk-abc123
            ```
        """
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
                # Only override if key exists and is a dict
                if key not in node or not isinstance(node[key], dict):
                    return  # Skip if path doesn't exist
                node = node[key]

            # Only override if final key exists
            if path[-1] in node:
                node[path[-1]] = Config._coerce_env_value(value)

        for env_key, env_value in os.environ.items():
            if delimiter in env_key:
                # Check for empty parts in the original split
                original_parts = env_key.split(delimiter)
                if any(not part.strip() for part in original_parts):
                    continue

                # Handle nested keys with delimiter (e.g., SECTION__KEY)
                parts = [p.strip() for p in original_parts if p.strip()]
                if parts:
                    set_nested(result, parts, env_value)
            else:
                # Handle flat keys (e.g., KEY) - only override existing keys
                if env_key in result:
                    result[env_key] = Config._coerce_env_value(env_value)

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
            expanded = expand_tilde_str(original_sval)
            return expanded

        return convert(data, ())

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
            return expand_tilde_str(s)

        return convert(data)

    def _collect_secret_paths_from_model(
        self, model_cls: type[BaseModel] | type[BaseSettings], prefix: Tuple[str, ...] = ()
    ) -> set[Tuple[str, ...]]:
        paths: set[Tuple[str, ...]] = set()
        fields = getattr(model_cls, "__pydantic_fields__", {})
        for name, field in fields.items():
            ann = getattr(field, "annotation", None)
            if self._is_secret_annotation(ann):
                paths.add(prefix + (name,))
                continue

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
    Configuration wrapper that automatically includes CoreSettings with environment variable support.

    CoreConfig is a convenience class that wraps the base Config class and automatically
    loads CoreSettings as the default configuration. This includes support for environment
    variables, .env files, and INI configuration files with automatic path expansion.

    Args:
        extra_settings: Additional configuration overrides (highest precedence)
        apply_env_overrides: Whether to apply environment variable overrides

    Examples:
        Basic usage with default CoreSettings:
        ```python
        from mindtrace.core.config import CoreConfig

        # Loads CoreSettings with env overrides
        config = CoreConfig()
        print(config.MINDTRACE_DEFAULT_HOST_URLS.SERVICE)
        ```

        With additional overrides:
        ```python
        config = CoreConfig({
            "MINDTRACE_DIR_PATHS": {
                "TEMP_DIR": "/custom/tmp"
            }
        })
        # Override takes precedence over CoreSettings defaults
        ```

        Environment variable overrides:
        ```python
        import os
        os.environ["MINDTRACE_DEFAULT_HOST_URLS__SERVICE"] = "http://custom:8000"

        config = CoreConfig()
        # Environment variable overrides the INI file value
        print(config.MINDTRACE_DEFAULT_HOST_URLS.SERVICE)  # http://custom:8000
        ```

    Note:
        Environment variables are applied at the CoreSettings level, not at the Config level.
        Additional overrides passed to CoreConfig take the highest precedence.
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
        super().__init__(extra_settings=extras, apply_env_overrides=False)
