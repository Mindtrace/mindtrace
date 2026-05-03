from __future__ import annotations

from abc import ABC, abstractmethod


class AbstractModelProviderPlugin(ABC):
    """Base class for model provider plugins.

    Register via pyproject.toml entry-points:
        [project.entry-points."mindtrace.model_providers"]
        my_provider = "my_package.providers:MyProvider"
    """

    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @property
    @abstractmethod
    def supported_model_ids(self) -> list[str]: ...


__all__ = ["AbstractModelProviderPlugin"]
