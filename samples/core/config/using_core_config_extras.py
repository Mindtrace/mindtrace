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
    MINDTRACE_SERVICE: ServiceCoreSettings= ServiceCoreSettings()



class Service(Mindtrace):
    def __init__(self):
        super().__init__(extra_settings=ServiceSettings(),
        )
    def instance_method(self):
        print(self.config['MINDTRACE_API_KEYS']['OPENAI']) # Accessing a config value from config_dict
        print(self.config['MINDTRACE_DIR_PATHS']['LOGGER_DIR'])



obj = Service()
obj.instance_method()
obj.config.save_json("config.json")
config = obj.config.load_json("config.json")
print(config['MINDTRACE_SERVICE']['MLFLOWPORT'])


