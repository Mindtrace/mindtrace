"""MinIO backend is a thin subclass of S3RegistryBackend."""

from mindtrace.registry.backends.minio_registry_backend import MinioRegistryBackend
from mindtrace.registry.backends.s3_registry_backend import S3RegistryBackend


def test_minio_registry_backend_is_s3_subclass():
    assert issubclass(MinioRegistryBackend, S3RegistryBackend)
