from mindtrace.registry.archivers.config_archiver import ConfigArchiver
from mindtrace.registry.archivers.default_archivers import register_default_materializers
from mindtrace.registry.archivers.path_archiver import PathArchiver
from mindtrace.registry.backends.local_registry_backend import LocalRegistryBackend
from mindtrace.registry.backends.registry_backend import RegistryBackend
from mindtrace.registry.backends.s3_registry_backend import MinioRegistryBackend, S3RegistryBackend
from mindtrace.registry.core.archiver import Archiver
from mindtrace.registry.core.exceptions import (
    LockTimeoutError,
    StoreAmbiguousObjectError,
    StoreKeyFormatError,
    StoreLocationNotFound,
)
from mindtrace.registry.core.registry import Registry
from mindtrace.registry.core.store import Store, StoreMount

__all__ = [
    "Archiver",
    "ConfigArchiver",
    "PathArchiver",
    "LocalRegistryBackend",
    "LockTimeoutError",
    "GCPRegistryBackend",
    "MinioRegistryBackend",
    "S3RegistryBackend",
    "Registry",
    "RegistryBackend",
    "Store",
    "StoreMount",
    "StoreLocationNotFound",
    "StoreKeyFormatError",
    "StoreAmbiguousObjectError",
    "Version",
]

register_default_materializers()


def __getattr__(name):
    if name == "GCPRegistryBackend":
        from mindtrace.registry.backends.gcp_registry_backend import GCPRegistryBackend

        globals()["GCPRegistryBackend"] = GCPRegistryBackend
        return GCPRegistryBackend
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
e__!r} has no attribute {name!r}")
