from mindtrace.database.backends.mindtrace_odm import InitMode, MindtraceODM
from mindtrace.database.backends.unified_odm import (
    BackendType,
    UnifiedMindtraceDocument,
    UnifiedMindtraceODM,
)
from mindtrace.database.core.exceptions import DocumentNotFoundError, DuplicateInsertError

__all__ = [
    "BackendType",
    "InitMode",
    "MindtraceODM",
    "DocumentNotFoundError",
    "DuplicateInsertError",
    "Link",
    "RegistryMindtraceODM",
    "MindtraceDocument",
    "MindtraceRedisDocument",
    "MongoMindtraceODM",
    "RedisMindtraceODM",
    "UnifiedMindtraceDocument",
    "UnifiedMindtraceODM",
]

_LAZY_IMPORTS = {
    "Link": ("beanie", "Link"),
    "MindtraceDocument": ("mindtrace.database.backends.mongo_odm", "MindtraceDocument"),
    "MongoMindtraceODM": ("mindtrace.database.backends.mongo_odm", "MongoMindtraceODM"),
    "MindtraceRedisDocument": ("mindtrace.database.backends.redis_odm", "MindtraceRedisDocument"),
    "RedisMindtraceODM": ("mindtrace.database.backends.redis_odm", "RedisMindtraceODM"),
    "RegistryMindtraceODM": ("mindtrace.database.backends.registry_odm", "RegistryMindtraceODM"),
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
