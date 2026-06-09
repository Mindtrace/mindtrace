## Mindtrace Config Usage Guide

The following guide explains `Config` usage provided in the `mindtrace-core` module.

1. [Integration with the Mindtrace Base Class](#integration-with-the-mindtrace-base-class)
    - [Reading Config Values](#reading-config-values)
    - [Class-level Access](#class-level-access)
    - [Overriding Config Values via Environment Variables](#overriding-config-values-via-environment-variables)
    - [Precedence Order of Config Values](#precedence-order-of-config-values)

2. [General Usage](#general-usage)
    - [Basic Access Patterns](#basic-access-patterns)
    - [Serializing Config](#serializing-config)
    - [Defining Module-specific Settings](#defining-module-specific-settings)
    - [Masking Sensitive Fields](#masking-sensitive-fields)

### Integration with the Mindtrace Base Class

The `Mindtrace` base class automatically provides a `Config` object as `self.config` (and `cls.config`).

`Config` is a `pydantic_settings.BaseSettings` subclass. It loads default values from the bundled `config.ini` and merges environment variables / `.env` overrides on top. The standard Mindtrace sections (`MINDTRACE_DIR_PATHS`, `MINDTRACE_DEFAULT_HOST_URLS`, `MINDTRACE_API_KEYS`, ...) are pre-declared as typed fields.

#### Reading Config Values

```python
from mindtrace.core import Mindtrace


class CustomComponent(Mindtrace):
    def show(self):
        print(self.config.MINDTRACE_DEFAULT_HOST_URLS.SERVICE)
        print(self.config.MINDTRACE_DIR_PATHS.TEMP_DIR)


CustomComponent().show()
```

#### Class-level Access

`config` is also available without instantiation:

```python
from mindtrace.core import Mindtrace

print(Mindtrace.config.MINDTRACE_DIR_PATHS.ROOT)
```

#### Overriding Config Values via Environment Variables

Environment variables take precedence over `config.ini` defaults. Use the `SECTION__KEY` delimiter:

```python
import os
from mindtrace.core import Mindtrace

os.environ["MINDTRACE_DEFAULT_HOST_URLS__SERVICE"] = "http://env-service:8080"

mt = Mindtrace()
print(mt.config.MINDTRACE_DEFAULT_HOST_URLS.SERVICE)  # http://env-service:8080
```

#### Precedence Order of Config Values

Highest → lowest:

1. Constructor kwargs (`Config(MINDTRACE_DEFAULT_HOST_URLS=...)`)
2. Environment variables (`SECTION__KEY` delimiter)
3. `.env` file
4. `config.ini` bundled with the package

### General Usage

#### Basic Access Patterns

```python
from mindtrace.core import Config

config = Config()

# Attribute style
print(config.MINDTRACE_DIR_PATHS.TEMP_DIR)

# Dict style
print(config["MINDTRACE_DIR_PATHS"]["TEMP_DIR"])

# .get() method
print(config.get("MINDTRACE_DIR_PATHS").get("TEMP_DIR"))
```

#### Serializing Config

```python
config = Config()

# Plain dict (with secret values revealed)
config.model_dump()

# JSON string (secrets revealed via field_serializer)
config.model_dump_json(indent=2)
```

#### Defining Module-specific Settings

If your module needs its own settings, define a sibling `BaseSettings` and instantiate it alongside `Config`. See [`cluster_module.py`](cluster_module.py) for a runnable example.

```python
from pathlib import Path
from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings


class MY_MODULE(BaseModel):
    API_KEY: SecretStr
    ENDPOINT: str


class MyModuleSettings(BaseSettings):
    MY_MODULE: MY_MODULE
    model_config = {
        "env_nested_delimiter": "__",
        "env_file": Path(__file__).parent / "my_module.env",
    }


settings = MyModuleSettings()
print(settings.MY_MODULE.ENDPOINT)
```

#### Masking Sensitive Fields

Secret fields declared as `pydantic.SecretStr` are masked on `repr()`. Reveal them explicitly when needed:

```python
from mindtrace.core import Config

config = Config()

# Masked when printed/repr'd
print(config.MINDTRACE_API_KEYS.OPENAI)  # SecretStr('**********')

# Revealed via get_secret
print(config.get_secret("MINDTRACE_API_KEYS", "OPENAI"))  # sk-...
```

`model_dump_json()` reveals secret values too, so be intentional about where you serialize.
