from mindtrace.core import Mindtrace
import os

class MyClass(Mindtrace):
    def __init__(self):
        super().__init__(extra_settings=[{
                                            'SERVICE': {
                                                'PORT': 8080,
                                                        },
                                            },
                                        {
                                            'CAMERA': {
                                                'RESOLUTION': 0.1,
                                                }
                                            },
        ])
    def instance_method(self):
        print(self.config['RABBITMQ']['PASSWORD']) # Accessing a config value from config_dict
        print(self.config['SERVICE']['PORT'])
        print(self.config.get('SERVICE').get('PORT'))
        print(self.config['CAMERA']['RESOLUTION'])

MyClass().instance_method()