#### Overriding Config

# When inheriting from the Mindtrace base class, 
# you can override configuration values directly by passing overrides at initialization.

# Example:
from mindtrace.core import Mindtrace, Config

class CustomMindtrace(Mindtrace):
    def __init__(self, **kwargs):
        # Example: override service URL and temp directory
        overrides = {
            "MINDTRACE_DEFAULT_HOST_URLS": {"SERVICE": "http://localhost:9000"},
            "MINDTRACE_DIR_PATHS": {"TEMP_DIR": "/custom/tmp"}
        }
        super().__init__(config_overrides=overrides, **kwargs)

# Usage
custom = CustomMindtrace()
print(custom.config.MINDTRACE_DEFAULT_HOST_URLS.SERVICE)   # http://localhost:9000

#### Extending Config
# When inheriting the Mindtrace class, you may want to extend the configuration with additional values.
# These extra values can come from a dict or a Pydantic model.

# For example, a ClusterModule might define its own config and inject it into the shared Config.

# Example:
from pydantic import BaseModel
from mindtrace.core import Mindtrace

class ClusterConfig(BaseModel):
    CLUSTER_REGISTRY: str = 'minio-registry'
    MINIO_BUCKET: str = 'minio-registry'

class ClusterModule(Mindtrace):
    def __init__(self, **kwargs):
        super().__init__(config_overrides=ClusterConfig(), **kwargs)

# Usage
cluster = ClusterModule()

print(cluster.config.CLUSTER_REGISTRY)      
print(cluster.config.MINIO_BUCKET)   

#### Cloning Config Without Overwriting Original
# Sometimes you may want to clone the existing config and modify it, without affecting the original.

from mindtrace.core import Mindtrace

mt = Mindtrace()

# Clone and override values safely
temp_config = mt.config.clone_with_overrides({"MINDTRACE_DIR_PATHS": {"TEMP_DIR": "/tmp/testing"}})

print(mt.config.MINDTRACE_DIR_PATHS.TEMP_DIR)      # Original value (unchanged)
print(temp_config.MINDTRACE_DIR_PATHS.TEMP_DIR)    # /tmp/testing



import os
from mindtrace.core import Mindtrace

# Step 1: Define environment variable (highest precedence after overrides)
os.environ["MINDTRACE_DEFAULT_HOST_URLS__SERVICE"] = "http://env-service:8080"

# Step 2: Initialize Mindtrace
mt = Mindtrace()

# Step 3: Runtime override beats env
override = {"MINDTRACE_DEFAULT_HOST_URLS": {"SERVICE": "http://runtime-override:9000"}}
mt_override = Mindtrace(config_overrides=override)

print(mt.config.MINDTRACE_DEFAULT_HOST_URLS.SERVICE)       # http://env-service:8080
print(mt_override.config.MINDTRACE_DEFAULT_HOST_URLS.SERVICE)  # http://runtime-override:9000