from mindtrace.registry.archivers.config_archiver import ConfigArchiver
from mindtrace.registry.backends.gcp_registry_backend import GCPRegistryBackend
from mindtrace.registry.backends.local_registry_backend import LocalRegistryBackend
from mindtrace.registry.backends.minio_registry_backend import MinioRegistryBackend
from mindtrace.registry.backends.registry_backend import RegistryBackend
from mindtrace.registry.core.archiver import Archiver
from mindtrace.registry.core.registry import LockTimeoutError, Registry
import mindtrace.registry.archivers.default_archivers  # Registers default archivers to the Registry class

from mindtrace.core import check_libs
if check_libs(["ultralytics", "torch"]) == []:
    # Registers the Ultralytics archivers to the Registry class
    import mindtrace.registry.archivers.ultralytics.yolo_archiver
    import mindtrace.registry.archivers.ultralytics.yoloe_archiver
    import mindtrace.registry.archivers.ultralytics.sam_archiver


__all__ = [
    "Archiver",
    "ConfigArchiver",
    "LocalRegistryBackend",
    "LockTimeoutError",
    "GCPRegistryBackend",
    "MinioRegistryBackend",
    "Registry",
    "RegistryBackend",
]
