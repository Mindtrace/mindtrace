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


class Inspectra(Service):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.add_endpoint("/config", self.config, schema=ConfigSchema)

    def config(self):
        return ConfigSchema(
            name="inspectra",
            description="Inspectra",
            version="1.0.0",
            author="Inspectra",
            author_email="inspectra@inspectra.com",
            url="https://inspectra.com",
        )
