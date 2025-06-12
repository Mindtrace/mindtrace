from mindtrace.core import Mindtrace
import os

class MyClass(Mindtrace):
    def __init__(self):
        super().__init__()
    def instance_method(self):
        print(self.config['RABBITMQ']['PASSWORD']) # Accessing a config value from config_dict
        print(self.config['API_KEYS']['OPENAI'].get_secret_value()) # Accessing a secret value from config_dict


os.environ['API_KEYS__OPENAI'] = 'sk-1234567890abcdef'
MyClass().instance_method()