import json
from pathlib import Path
from mindtrace.core import Mindtrace
from pydantic_settings import BaseSettings
from pydantic import BaseModel
from mindtrace.core.config import CoreSettings
from mindtrace.core.config import Config


class ServiceCoreSettings(BaseModel):
    MLFLOWPORT: int = 8000

class ServiceSettings(CoreSettings):
    SERVICE: ServiceCoreSettings= ServiceCoreSettings()



class Service(Mindtrace):
    def __init__(self):
        super().__init__(extra_settings=[ServiceSettings(),
        ])
    def instance_method(self):
        print(self.config['RABBITMQ']['PASSWORD'].get_secret_value()) # Accessing a config value from config_dict
        print(self.config['SERVICE']['MLFLOWPORT'])

    def save_config(self, path: str | Path = "config_snapshot.json"):
        with open(path, "w") as f:
            json.dump(ServiceSettings(**self.config).model_dump(mode='json'), f, indent=4)
    
    def load_config(self, path: str | Path = "config_snapshot.json") -> ServiceSettings:
        with open(path, "r") as f:
            config_data = json.load(f)
        self.config = Config(ServiceSettings(**config_data))
        
# the example showcase a sample usage of CoreSettings inheritance and self.config dictionary from Mindtrace Base class
# Service class adds extra settings to the config, during initialization
# stores the new config in json format and loads it back
obj = Service()
obj.instance_method()
# save the config, note :below method will not save the secret strings, until explicitly written
obj.save_config()
# load the stored config
print('#########################')
obj.load_config()
print(obj.config['SERVICE']['MLFLOWPORT'])
print(obj.config['RABBITMQ']['PASSWORD'].get_secret_value())