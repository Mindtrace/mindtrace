import os


class Config(dict):
    """Template Config class."""

    def __init__(self, **kwargs):
        default_config = {
            "MINDTRACE_TEMP_DIR": "~/.cache/mindtrace/temp",
            "MINDTRACE_DEFAULT_REGISTRY_DIR": "~/.cache/mindtrace/registry",
            "MINDTRACE_CLUSTER_DEFAULT_REGISTRY_DIR": "~/.cache/mindtrace/cluster/registry",
            "MINDTRACE_DEFAULT_HOST_URLS": {
                "Service": "http://localhost:8000",
                "ClusterManager": "http://localhost:8090",
            },
            "MINDTRACE_MINIO_REGISTRY_URI": "~/.cache/mindtrace/minio-registry",
            "MINDTRACE_MINIO_ENDPOINT": "localhost:9000",
            "MINDTRACE_MINIO_ACCESS_KEY": "minioadmin",
            "MINDTRACE_MINIO_SECRET_KEY": "minioadmin",
            "MINDTRACE_SERVER_PIDS_DIR_PATH": "~/.cache/mindtrace/pids",
            "MINDTRACE_LOGGER_DIR": "~/.cache/mindtrace/logs",
            "MINDTRACE_CLUSTER_DEFAULT_REDIS_URL": "redis://localhost:6379",
            "MINDTRACE_CLUSTER_MINIO_ENDPOINT": "localhost:9000",
            "MINDTRACE_CLUSTER_MINIO_ACCESS_KEY": "minioadmin",
            "MINDTRACE_CLUSTER_MINIO_SECRET_KEY": "minioadmin",
            "MINDTRACE_CLUSTER_MINIO_BUCKET": "minio-registry",
            "MINDTRACE_WORKER_REDIS_DEFAULT_URL": "redis://localhost:6379",
            "MINDTRACE_MCP_MOUNT_PATH": "/mcp-server",
            "MINDTRACE_MCP_HTTP_APP_PATH": "/mcp",
        }
        # Update defaults with any provided kwargs
        default_config.update(kwargs)
        # Expand ~ only if it is at the start of the string
        for k, v in default_config.items():
            if isinstance(v, str) and v.startswith("~/"):
                default_config[k] = os.path.expanduser(v)
        super().__init__(default_config)
