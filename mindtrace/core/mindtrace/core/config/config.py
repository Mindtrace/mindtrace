class Config(dict):
    """Template Config class."""
    
    def __init__(self, **kwargs):
        default_config = {
            "MINDTRACE_TEMP_DIR": "~/.cache/mindtrace/temp",
            "MINDTRACE_DEFAULT_REGISTRY_DIR": "~/.cache/mindtrace/registry",
            "MINDTRACE_DEFAULT_HOST_URLS": {
                "Service": "http://localhost:8000",
            },
            "MINDTRACE_DEFAULT_LOG_DIR": "~/.cache/mindtrace/logs",
            "MINDTRACE_MINIO_REGISTRY_URI": "~/.cache/mindtrace/minio-registry",
            "MINDTRACE_MINIO_ENDPOINT": "localhost:9000",
            "MINDTRACE_MINIO_ACCESS_KEY": "minioadmin",
            "MINDTRACE_MINIO_SECRET_KEY": "minioadmin",
            "MINDTRACE_SERVER_PIDS_DIR_PATH": "~/.cache/mindtrace/pids",
        }
        # Update defaults with any provided kwargs
        default_config.update(kwargs)
        super().__init__(default_config)
