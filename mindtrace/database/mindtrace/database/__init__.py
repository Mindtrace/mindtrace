# Re-export commonly used Beanie types for convenience
from beanie import Link

from mindtrace.database.backends.mindtrace_odm import InitMode, MindtraceODM
from mindtrace.database.backends.mongo_odm import MindtraceDocument, MongoMindtraceODM
from mindtrace.database.backends.redis_odm import MindtraceRedisDocument, RedisMindtraceODM
from mindtrace.database.backends.unified_odm import (
    BackendType,
    UnifiedMindtraceDocument,
    UnifiedMindtraceODM,
)
from mindtrace.database.core.exceptions import DocumentNotFoundError, DuplicateInsertError, QueryNotSupported

__all__ = [
    "BackendType",
    "InitMode",
    "MindtraceODM",
    "DocumentNotFoundError",
    "DuplicateInsertError",
    "Link",
    "MindtraceDocument",
    "MindtraceRedisDocument",
    "MongoMindtraceODM",
    "RedisMindtraceODM",
    "UnifiedMindtraceDocument",
    "UnifiedMindtraceODM",
    "QueryNotSupported",
]

