"""Registry bridge for connecting a Tracker to a model registry.

Provides a thin adapter layer so that :meth:`Tracker.log_model
<mindtrace.models.tracking.tracker.Tracker.log_model>` can delegate
persistence to an external model registry (e.g.
:class:`mindtrace.registry.Registry`) without requiring the tracker to
know about the registry's concrete API.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class RegistryProtocol(Protocol):
    """Structural protocol for objects that can act as a model registry.

    Any object that exposes a ``save(key, model)`` method satisfies this
    protocol and can be used with :class:`RegistryBridge`.
    """

    def save(self, key: str, model: Any) -> None:
        """Persist ``model`` under the given ``key``.

        Args:
            key: Unique storage key, typically formatted as
                ``"<name>:<version>"``.
            model: Model object to persist.
        """
        ...


class RegistryBridge:
    """Thin adapter between :class:`~mindtrace.models.tracking.tracker.Tracker`
    and an external model registry.

    A ``RegistryBridge`` wraps any registry object that exposes a
    ``save(key, model)`` method and translates the tracker's ``(name, version)``
    pair into the ``"<name>:<version>"`` key format expected by
    :class:`mindtrace.registry.Registry`.

    This keeps tracker backends decoupled from the concrete registry
    implementation: a tracker receives a ``RegistryBridge`` and calls
    :meth:`save`, delegating the actual persistence details to the
    underlying registry.

    Args:
        registry: Any object that satisfies :class:`RegistryProtocol`, i.e.
            exposes ``registry.save(key, model)``.

    Raises:
        TypeError: If ``registry`` does not satisfy :class:`RegistryProtocol`.

    Example:
        ```python
        from mindtrace.registry import Registry
        from mindtrace.models.tracking.registry_bridge import RegistryBridge

        registry = Registry(uri="s3://my-bucket/models")
        bridge = RegistryBridge(registry)

        key = bridge.save(model, name="resnet50", version="v1.2.0")
        print(key)  # "resnet50:v1.2.0"
        ```
    """

    def __init__(self, registry: Any) -> None:
        """Initialise the bridge with a registry instance.

        Args:
            registry: Registry object that exposes ``save(key, model)``.

        Raises:
            TypeError: If ``registry`` does not expose a callable ``save``
                attribute.
        """
        if not isinstance(registry, RegistryProtocol):
            raise TypeError(
                f"registry must implement the RegistryProtocol (i.e. have a "
                f"'save(key, model)' method). Got: {type(registry).__name__!r}."
            )
        self.registry = registry
        logger.debug("RegistryBridge initialised with registry: %s", type(registry).__name__)

    def save(self, model: Any, name: str, version: str) -> str:
        """Save a model to the registry and return the registry key.

        Formats the storage key as ``"<name>:<version>"`` and delegates to
        ``self.registry.save(key, model)``.

        Args:
            model: Model object to persist.
            name: Model name component of the registry key.
            version: Version string component of the registry key.

        Returns:
            The registry key used to store the model, formatted as
            ``"<name>:<version>"``.

        Example:
            ```python
            key = bridge.save(model, name="mobilenet_v3", version="2.0.0")
            # key == "mobilenet_v3:2.0.0"
            ```
        """
        key = f"{name}:{version}"
        logger.debug("Saving model to registry: key=%s", key)
        self.registry.save(key, model)
        logger.info("Model saved to registry: key=%s", key)
        return key


__all__ = [
    "RegistryBridge",
    "RegistryProtocol",
]
