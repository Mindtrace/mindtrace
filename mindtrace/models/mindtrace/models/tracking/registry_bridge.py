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

    Any object that exposes a ``save(name, obj, *, version=...)`` method
    satisfies this protocol and can be used with :class:`RegistryBridge`.  This
    mirrors :meth:`mindtrace.registry.Registry.save`, where the object *name*
    and its *version* are distinct arguments — the registry owns versioning.
    """

    def save(self, name: str, obj: Any, *, version: str | None = None) -> Any:
        """Persist ``obj`` under ``name`` at the given ``version``.

        Args:
            name: Registry object name (e.g. ``"detectors:yolov8"``).
            obj: Model object to persist.
            version: Explicit version string.  ``None`` lets the registry
                auto-assign the next version.
        """
        ...


class RegistryBridge:
    """Thin adapter between :class:`~mindtrace.models.tracking.tracker.Tracker`
    and an external model registry.

    A ``RegistryBridge`` wraps any registry object that exposes a
    ``save(name, obj, *, version=...)`` method and forwards the tracker's
    ``(name, version)`` pair to it directly, letting the registry own
    versioning — matching :class:`mindtrace.registry.Registry`.

    This keeps tracker backends decoupled from the concrete registry
    implementation: a tracker receives a ``RegistryBridge`` and calls
    :meth:`save`, delegating the actual persistence details to the
    underlying registry.

    Args:
        registry: Any object that satisfies :class:`RegistryProtocol`, i.e.
            exposes ``registry.save(name, obj, *, version=...)``.

    Raises:
        TypeError: If ``registry`` does not satisfy :class:`RegistryProtocol`.

    Example:
        ```python
        from mindtrace.registry import Registry
        from mindtrace.models.tracking.registry_bridge import RegistryBridge

        registry = Registry(uri="s3://my-bucket/models")
        bridge = RegistryBridge(registry)

        ref = bridge.save(model, name="resnet50", version="v1.2.0")
        print(ref)  # "resnet50:v1.2.0"
        ```
    """

    def __init__(self, registry: Any) -> None:
        """Initialise the bridge with a registry instance.

        Args:
            registry: Registry object that exposes
                ``save(name, obj, *, version=...)``.

        Raises:
            TypeError: If ``registry`` does not expose a callable ``save``
                attribute.
        """
        if not isinstance(registry, RegistryProtocol):
            raise TypeError(
                f"registry must implement the RegistryProtocol (i.e. have a "
                f"'save(name, obj, *, version=...)' method). Got: {type(registry).__name__!r}."
            )
        self.registry = registry
        logger.debug("RegistryBridge initialised with registry: %s", type(registry).__name__)

    def save(self, model: Any, name: str, version: str) -> str:
        """Save a model to the registry and return a ``"<name>:<version>"`` reference.

        Forwards ``name`` and ``version`` to ``self.registry.save`` as distinct
        arguments (``registry.save(name, model, version=version)``) so the
        registry versions the model correctly — the version must *not* be baked
        into the name.

        Args:
            model: Model object to persist.
            name: Registry object name.
            version: Explicit version string passed to the registry.

        Returns:
            A human-readable reference to the saved model version, formatted as
            ``"<name>:<version>"``.

        Example:
            ```python
            ref = bridge.save(model, name="mobilenet_v3", version="2.0.0")
            # ref == "mobilenet_v3:2.0.0"
            ```
        """
        logger.debug("Saving model to registry: name=%s version=%s", name, version)
        self.registry.save(name, model, version=version)
        ref = f"{name}:{version}"
        logger.info("Model saved to registry: %s", ref)
        return ref


__all__ = [
    "RegistryBridge",
    "RegistryProtocol",
]
