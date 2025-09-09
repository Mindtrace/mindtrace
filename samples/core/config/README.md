## Mindtrace Config Usage Guide

The following guide explains Config usage provided in the `mindtrace-core` module.


1. [Integration with Mindtrace Class](#integration-with-mindtrace-base-class)
    - [Overriding Config Parameters](#overriding-config-parameters)  
    - [Extending Config Parameters](#extending-config-parameters)
    - [Extending Config in Modules (Advanced)](#extending-config-in-modules-advanced)
    - [Cloning Config Without Overwriting Original](#cloning-config-without-overwriting-original)
    - [Precedence Order of Config Values](#precedence-order-of-config-values)
 
2. [General Usage](#general-usage)
    -   [Full Example: Load -> Override -> Save -> Reload -> Clone](#full-example-load---override---save---reload---clone)
    -   [Masking Sensitive Fields](#masking-sensitive-fields)

### Integration with Mindtrace Base Class

The `Mindtrace` base class automatically provides a `CoreConfig` object, initialized with CoreSettings.
- CoreSettings  is `Pydantic Setting` which loads default values from config.ini file.
- Any value can be overridden with environment variables using the ENV_VAR__NESTED_KEY format (e.g., MINDTRACE_API_KEYS__OPENAI=value).
- At inheritance or composition, these core settings can be overridden or extended using the config_overrides argument.

#### Overriding Config Parameters

When inheriting from the Mindtrace base class, you can override configuration values directly by passing overrides at initialization.

```python
from mindtrace.core import Mindtrace, Config

class CustomMindtrace(Mindtrace):
    def __init__(self, **kwargs):
        # Example: override service URL and temp directory
        overrides = {
            "MINDTRACE_DEFAULT_HOST_URLS": {"SERVICE": "http://localhost:9000"},
            "MINDTRACE_DIR_PATHS": {"TEMP_DIR": "/custom/tmp"}
        }
        super().__init__(config_overrides=overrides, **kwargs)

# Usage
custom = CustomMindtrace()
print(custom.config.MINDTRACE_DEFAULT_HOST_URLS.SERVICE)   # http://localhost:9000
```

#### Extending Config Parameters
When inheriting the Mindtrace class, you may want to extend the configuration with additional values.
These extra values can come from a dict or a Pydantic model.

For example, a ClusterModule might define its own config and inject it into the shared Config.

```python
from pydantic import BaseModel
from mindtrace.core import Mindtrace, Config

class ClusterConfig(BaseModel):
    CLUSTER_REGISTRY: str = 'minio-registry'
    MINIO_BUCKET: str = 'minio-registry'

class ClusterModule(Mindtrace):
    def __init__(self, **kwargs):
        super().__init__(config_overrides=ClusterConfig(), **kwargs)

# Usage
cluster = ClusterModule()

print(cluster.config.CLUSTER_REGISTRY)
print(cluster.config.MINIO_BUCKET)   
```

#### Extending Config in Modules (Advanced)
For module authors who want their settings to load automatically optionally merge with the core config, can wire it using `extra_settings`.

The below example define a Pydantic `BaseSettings` model with nested fields and wire it into the core via `CoreConfig` using `extra_settings`.

Example (see [cluster_module.py](../../../samples/core/config/cluster_module.py)):

#### Cloning Config Without Overwriting Original
Sometimes you may want to clone the existing config and modify it, without affecting the original.

```python
from mindtrace.core import Mindtrace

mt = Mindtrace()

# Clone and override values safely
temp_config = mt.config.clone_with_overrides({"MINDTRACE_DIR_PATHS": {"TEMP_DIR": "/tmp/testing"}})

print(mt.config.MINDTRACE_DIR_PATHS.TEMP_DIR)      # Original value (unchanged)
print(temp_config.MINDTRACE_DIR_PATHS.TEMP_DIR)    # /tmp/testing
```



#### Precedence Order of Config Values
Config values are resolved in the following order (highest → lowest):
1.  Runtime overrides passed
2.	Environment variables (ENV_VAR__NESTED_KEY)
3.	Defaults from CoreSettings

```python
import os
from mindtrace.core import Mindtrace

# Step 1: Define environment variable (highest precedence after overrides)
os.environ["MINDTRACE_DEFAULT_HOST_URLS__SERVICE"] = "http://env-service:8080"

# Step 2: Initialize Mindtrace
mt = Mindtrace()

# Step 3: Runtime override beats env
override = {"MINDTRACE_DEFAULT_HOST_URLS": {"SERVICE": "http://runtime-override:9000"}}
mt_override = Mindtrace(config_overrides=override)

print(mt.config.MINDTRACE_DEFAULT_HOST_URLS.SERVICE)       # http://env-service:8080
print(mt_override.config.MINDTRACE_DEFAULT_HOST_URLS.SERVICE)  # http://runtime-override:9000
```


### General Usage

Config can be utilized by any module looking to load or save SettingsLike objects—such as dict, Pydantic BaseModel, or BaseSettings—into a unified configuration object. This provides:
- A single interface for accessing deeply nested configurations
- Support for environment variable overrides (ENV_VAR__NESTED_KEY)
- Path normalization with '~' expansion
- Access values in attribute or dict-style
- Easy cloning and safe overrides without affecting original config
- JSON export/import


#### Full Example: Load -> Override -> Save -> Reload -> Clone
You can write a custom loader function as per your module’s requirements. The Config class enables saving the configuration to disk (optionally hiding secrets) and loading it back with consistency.

```python
import os
from pathlib import Path
from mindtrace.core.config import Config, load_ini_as_dict

# Step 1: Define your custom loader (e.g., from INI file)
def my_loader():
    file_path = os.path.join(os.path.dirname(__file__), "sample.ini")
    if Path(file_path).exists():
        return load_ini_as_dict(Path(file_path))
    else:
        raise FileNotFoundError("sample.ini not found")

# Step 2: Load configuration with defaults and overrides
defaults = my_loader()  # e.g., from INI
overrides = {
    "MINDTRACE_DIR_PATHS": {
        "TEMP_DIR": "/tmp/logs",
        "REGISTRY_DIR": "/tmp/registry"
    }
}

config = Config.load(defaults=defaults, overrides=overrides)

# Step 3: Access values (attribute or dict-style)
print("attribute style access", config.MINDTRACE_DIR_PATHS.TEMP_DIR)
print("dict style access", config["MINDTRACE_DIR_PATHS"]["TEMP_DIR"])
print("get method", config.get("MINDTRACE_DIR_PATHS").get("TEMP_DIR"))

# Step 4: Save config to JSON
config.save_json("saved_config.json")

# Step 5: Load config back
reloaded = Config.load_json("saved_config.json")

# Step 6: Clone config with more changes
cloned = reloaded.clone_with_overrides({
    "MINDTRACE_DIR_PATHS": {
        "TEMP_DIR": "/tmp/clone/logs"
    }
})

print("Original:", reloaded.MINDTRACE_DIR_PATHS.TEMP_DIR) 
print("Cloned:", cloned.MINDTRACE_DIR_PATHS.TEMP_DIR)     
```


#### Masking Sensitive Fields

The Config class preserves secret masking feature of Pydantic’s SecretStr field type. If you’re looking to add configuration values that should be hidden from logs, JSON output, or saved files (like API keys, passwords, etc.), you can define those fields using pydantic.SecretStr. 

When passed into the Config object, these fields will be masked as ********, but the real value is still safely stored and can be accessed when needed.

```python
from pydantic import BaseModel, SecretStr
from mindtrace.core.config import Config

# Step 1: Define your secret config fields
class APIKeys(BaseModel):
    OPENAI: SecretStr
    DISCORD: SecretStr

class AppSettings(BaseModel):
    API_KEYS: APIKeys

config = Config(AppSettings(API_KEYS=APIKeys(
    OPENAI=SecretStr("sk-abc123"),
    DISCORD=SecretStr("discord-token")
)))

# Step 2: Access the values (masked by default) under the namespace
print(config.API_KEYS.OPENAI)           # ********
print(config.API_KEYS.DISCORD)          # ********

# Step 3: Get the real values when needed
print(config.get_secret("API_KEYS", "OPENAI"))   # sk-abc123
print(config.get_secret("API_KEYS", "DISCORD"))   # discord-token
```




