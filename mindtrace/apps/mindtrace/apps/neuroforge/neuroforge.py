from pydantic import BaseModel

from mindtrace.core import TaskSchema
from mindtrace.services import services


class Config(BaseModel):
    name: str
    description: str
    version: str
    author: str
    author_email: str
    url: str

class ConfigSchema(TaskSchema):
    name: str
    description: str
    version: str
    author: str
    author_email: str
    url: str

class Neuroforge(Service):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    self.add_endpoint("/config", self.config, schema=ConfigSchema)
    self.add_endpoint("/another_method", self.another_method, schema=AnotherMethodSchema)

    def config(self):
        return ConfigSchema(
            name="neuroforge",
            description="Neuroforge",
            version="1.0.0",
            author="Neuroforge",
            author_email="neuroforge@neuroforge.com",
            url="https://neuroforge.com",
        )


    def another_method(self):
        raise NotImplementedError("This method is not implemented")
