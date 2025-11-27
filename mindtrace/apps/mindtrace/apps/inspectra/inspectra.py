from pydantic import BaseModel

from mindtrace.core import TaskSchema
from mindtrace.services import Service

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
    """
    Inspectra root service definition.
    This registers Inspectra with the Mindtrace service layer,
    and exposes internal RPC endpoints such as `/config`.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Register endpoints
        self.add_endpoint("/config", self.config, schema=ConfigSchema)

    def config(self) -> ConfigSchema:
        """
        Returns the Inspectra metadata.
        """
        return ConfigSchema(
            name="inspectra",
            description="Inspectra Manufacturing Intelligence Platform",
            version="1.0.0",
            author="Inspectra",
            author_email="inspectra@inspectra.com",
            url="https://inspectra.com",
        )
