__all__ = ["ClusterManager", "Node", "Worker", "ProxyWorker", "StandardWorkerLauncher"]

_LAZY_IMPORTS = {
    "ClusterManager": ("mindtrace.cluster.core.cluster_manager", "ClusterManager"),
    "Node": ("mindtrace.cluster.core.node", "Node"),
    "Worker": ("mindtrace.cluster.core.worker", "Worker"),
    "StandardWorkerLauncher": ("mindtrace.cluster.core.archiver", "StandardWorkerLauncher"),
    "ProxyWorker": ("mindtrace.cluster.core.types", "ProxyWorker"),
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
