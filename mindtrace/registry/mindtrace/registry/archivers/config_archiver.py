import json
from pathlib import Path
from typing import Any, Type

from mindtrace.core import Config
from mindtrace.registry.core.archiver import Archiver


class ConfigArchiver(Archiver):
    """Archiver for mindtrace.core.Config objects."""

    def __init__(self, uri: str, **kwargs):
        super().__init__(uri=uri, **kwargs)

    def save(self, config: Config):
        with open(Path(self.uri) / "config.json", "w") as f:
            json.dump(config.model_dump(mode="json"), f)

    def load(self, data_type: Type[Any]) -> Config:
        with open(Path(self.uri) / "config.json", "r") as f:
            return Config(**json.load(f))
