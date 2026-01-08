from mindtrace.core import check_libs
from mindtrace.registry.archivers.config_archiver import ConfigArchiver
from mindtrace.registry.archivers.default_archivers import (
    register_default_materializers,  # Registers default archivers to the Registry class
)
from mindtrace.registry.archivers.path_archiver import PathArchiver
from mindtrace.registry.backends.gcp_registry_backend import GCPRegistryBackend
from mindtrace.registry.backends.local_registry_backend import LocalRegistryBackend
from mindtrace.registry.backends.s3_registry_backend import S3RegistryBackend
from mindtrace.registry.backends.registry_backend import RegistryBackend
from mindtrace.registry.core.archiver import Archiver
from mindtrace.registry.core.exceptions import LockTimeoutError
from mindtrace.registry.core.registry import Registry
from mindtrace.registry.core.registry_with_cache import RegistryWithCache

if check_libs(["ultralytics", "torch"]) == []:
    # Registers the Ultralytics archivers to the Registry class
    import mindtrace.registry.archivers.ultralytics.sam_archiver  # noqa: F401
    import mindtrace.registry.archivers.ultralytics.yolo_archiver  # noqa: F401
    import mindtrace.registry.archivers.ultralytics.yoloe_archiver  # noqa: F401


__all__ = [
    "Archiver",
    "ConfigArchiver",
    "PathArchiver",
    "LocalRegistryBackend",
    "LockTimeoutError",
    "GCPRegistryBackend",
    "S3RegistryBackend",
    "Registry",
    "RegistryBackend",
    "RegistryWithCache",
]

register_default_materializers()
