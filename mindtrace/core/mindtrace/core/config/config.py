class Config(dict):
    """Template Config class."""
    
    def __init__(self, **kwargs):
        default_config = {
            "MINDTRACE_TEMP_DIR": "~/.cache/mindtrace/temp",
            "MINDTRACE_DEFAULT_REGISTRY_DIR": "~/.cache/mindtrace/registry",
            "MINDTRACE_MINIO_REGISTRY_URI": "~/.cache/mindtrace/minio-registry",
        }
        # Update defaults with any provided kwargs
        default_config.update(kwargs)
        super().__init__(default_config)
