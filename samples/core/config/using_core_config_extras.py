import json
from pathlib import Path
from mindtrace.core import Mindtrace
from pydantic_settings import BaseSettings
from pydantic import BaseModel
from mindtrace.core.config import CoreSettings
from mindtrace.core.config import Config
from pydantic import SecretStr, AnyUrl



class ServiceCoreSettings(BaseModel):
    MLFLOWPORT: int = 8000

class ServiceSettings(CoreSettings):
    SERVICE: ServiceCoreSettings= ServiceCoreSettings()



class Service(Mindtrace):
    def __init__(self):
        super().__init__(extra_settings=ServiceSettings(),
        )
    def instance_method(self):
        print(self.config['MINDTRACE_API_KEYS']['OPENAI']) # Accessing a config value from config_dict
        print(self.config['MINDTRACE_DIR_PATHS']['LOGGER_DIR'])

    def save_config(self, path: str | Path = "config_snapshot.json", reveal_secrets: bool = False) -> None:
        data = _config_to_json_dict(self.config, reveal_secrets=reveal_secrets)
        with open(path, "w") as f:
            json.dump(data, f, indent=4)
    
    def load_config(self, path: str | Path = "config_snapshot.json") -> None:
        with open(path, "r") as f:
            data = json.load(f)
        # Merges file content over defaults and then overlays env vars
        self.config = Config(extra_settings=data)


def _config_to_json_dict(cfg: dict, reveal_secrets: bool = False) -> dict:
    def convert(v):
        if isinstance(v, SecretStr):
            return v.get_secret_value() if reveal_secrets else "********"
        if isinstance(v, AnyUrl):
            return str(v)
        if isinstance(v, dict):
            return {k: convert(x) for k, x in v.items()}
        if isinstance(v, (list, tuple, set)):
            return [convert(x) for x in v]
        return v
    return convert(cfg)

# the example showcase a sample usage of CoreSettings inheritance and self.config dictionary from Mindtrace Base class
# Service class adds extra settings to the config, during initialization
# stores the new config in json format and loads it back
obj = Service()
obj.instance_method()
# save the config, note :below method will not save the secret strings, until explicitly written
obj.save_config(reveal_secrets=True)
# load the stored config
# print('#########################')
obj.load_config()
print(obj.config['SERVICE']['MLFLOWPORT'])
