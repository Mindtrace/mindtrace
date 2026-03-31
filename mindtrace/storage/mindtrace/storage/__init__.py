from mindtrace.storage.base import BatchResult, FileResult, Status, StorageHandler, StringResult
from mindtrace.storage.s3 import S3StorageHandler

__all__ = [
    "BatchResult",
    "FileResult",
    "GCSStorageHandler",
    "S3StorageHandler",
    "StorageHandler",
    "StringResult",
    "Status",
]


def __getattr__(name):
    if name == "GCSStorageHandler":
        from mindtrace.storage.gcs import GCSStorageHandler

        globals()["GCSStorageHandler"] = GCSStorageHandler
        return GCSStorageHandler
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
