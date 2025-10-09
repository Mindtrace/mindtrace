import os
from pathlib import Path

from mindtrace.core.config import Config
from mindtrace.core.utils import load_ini_as_dict


# Step 1: Define your custom loader (e.g., from INI file)
def my_loader():
    file_path = os.path.join(os.path.dirname(__file__), "sample.ini")
    if Path(file_path).exists():
        return load_ini_as_dict(Path(file_path))
    else:
        raise FileNotFoundError("sample.ini not found")


# Step 2: Load configuration with defaults and overrides
defaults = my_loader()  # e.g., from INI
overrides = {"MINDTRACE_DIR_PATHS": {"TEMP_DIR": "/tmp/logs", "REGISTRY_DIR": "/tmp/registry"}}

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
cloned = reloaded.clone_with_overrides({"MINDTRACE_DIR_PATHS": {"TEMP_DIR": "/tmp/clone/logs"}})

print("Original:", reloaded.MINDTRACE_DIR_PATHS.TEMP_DIR)  # May be "INFO"
print("Cloned:", cloned.MINDTRACE_DIR_PATHS.TEMP_DIR)  # "DEBUG"


##### Masking Sensitive Fields

from pydantic import BaseModel, SecretStr

from mindtrace.core.config import Config


# Step 1: Define your secret config fields
class APIKeys(BaseModel):
    OPENAI: SecretStr
    DISCORD: SecretStr


class AppSettings(BaseModel):
    API_KEYS: APIKeys


config = Config(AppSettings(API_KEYS=APIKeys(OPENAI=SecretStr("sk-abc123"), DISCORD=SecretStr("discord-token"))))

# Step 2: Access the values (masked by default) under the namespace
print(config.API_KEYS.OPENAI)  # ********
print(config.API_KEYS.DISCORD)  # ********

# Step 3: Get the real values when needed
print(config.get_secret("API_KEYS", "OPENAI"))  # sk-abc123
print(config.get_secret("API_KEYS", "DISCORD"))  # discord-token
