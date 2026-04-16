from mindtrace.registry.backends.local_registry_backend import LocalRegistryBackend
from mindtrace.registry.backends.registry_backend import RegistryBackend
from mindtrace.registry.core.exceptions import (
    LockTimeoutError,
    StoreAmbiguousObjectError,
    StoreKeyFormatError,
    StoreLocationNotFound,
)
from mindtrace.registry.core.mount import (
    AmbientAuth,
    GCSMountConfig,
    GCSServiceAccountFileAuth,
    LocalMountConfig,
    Mount,
    MountBackendKind,
    NoAuth,
    S3AccessKeyAuth,
    S3MountConfig,
)
from mindtrace.registry.core.registry import Registry
from mindtrace.registry.core.store import MountedRegistry, Store

__all__ = [
    "Archiver",
    "AmbientAuth",
    "ConfigArchiver",
    "PathArchiver",
    "LocalRegistryBackend",
    "LockTimeoutError",
    "GCSMountConfig",
    "GCPRegistryBackend",
    "GCSServiceAccountFileAuth",
    "LocalMountConfig",
    "MinioRegistryBackend",
    "Mount",
    "MountBackendKind",
    "NoAuth",
    "S3AccessKeyAuth",
    "S3MountConfig",
    "S3RegistryBackend",
    "Registry",
    "RegistryBackend",
    "Store",
    "MountedRegistry",
    "StoreMount",
    "StoreLocationNotFound",
    "StoreKeyFormatError",
    "StoreAmbiguousObjectError",
]

_lazy_registry_initialized = False


def _ensure_default_materializers():
    global _lazy_registry_initialized
    if not _lazy_registry_initialized:
        _lazy_registry_initialized = True
        from mindtrace.registry.archivers.default_archivers import register_default_materializers

        register_default_materializers()


_LAZY_IMPORTS = {
    "Archiver": ("mindtrace.registry.core.archiver", "Archiver"),
    "ConfigArchiver": ("mindtrace.registry.archivers.config_archiver", "ConfigArchiver"),
    "PathArchiver": ("mindtrace.registry.archivers.path_archiver", "PathArchiver"),
    "S3RegistryBackend": ("mindtrace.registry.backends.s3_registry_backend", "S3RegistryBackend"),
    "MinioRegistryBackend": ("mindtrace.registry.backends.s3_registry_backend", "MinioRegistryBackend"),
    "GCPRegistryBackend": ("mindtrace.registry.backends.gcp_registry_backend", "GCPRegistryBackend"),
}


def __getattr__(name):
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        import importlib

        mod = importlib.import_module(module_path)
        val = getattr(mod, attr)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
