from pathlib import Path
from typing import Any

from pydantic import BaseModel

from mindtrace.registry.backends.registry_backend import RegistryBackend


class GCPRegistryBackend(RegistryBackend):  # pragma: no cover
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def push(self, name: str, version: str, local_path: str | Path):
        raise NotImplementedError("Registry push method not implemented")

    def pull(self, name: str, version: str, local_path: str | Path):
        raise NotImplementedError("Registry pull method not implemented")

    def delete(self, name: str, version: str | None = None):
        raise NotImplementedError("Registry delete method not implemented")

