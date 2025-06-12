from mindtrace.core import Mindtrace
from pydantic_settings import BaseSettings


class ServiceSettings(BaseSettings):
    MLFLOWPORT: int = 8000

class CameraSettings(BaseSettings):
    CAM_RESOLUTION: float = 1.0


class MyClass(Mindtrace):
    def __init__(self):
        super().__init__(extra_settings=[ServiceSettings().model_dump(),
                                         CameraSettings().model_dump()
        ])
    def instance_method(self):
        print(self.config['RABBITMQ']['PASSWORD']) # Accessing a config value from config_dict
        print(self.config['MLFLOWPORT'])
        print(self.config.get('CAM_RESOLUTION'))

MyClass().instance_method()