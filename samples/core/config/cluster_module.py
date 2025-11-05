from pathlib import Path

from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings

from mindtrace.core import Mindtrace
from mindtrace.core.config import CoreConfig, SettingsLike


class MINDTRACE_CLUSTER(BaseModel):
    DEFAULT_REDIS_URL: str
    MINIO_ENDPOINT: str
    MINIO_ACCESS_KEY: SecretStr
    MINIO_SECRET_KEY: SecretStr
    MINIO_BUCKET: str


class ClusterSettings(BaseSettings):
    MINDTRACE_CLUSTER: MINDTRACE_CLUSTER
    model_config = {"env_nested_delimiter": "__", "env_file": Path(__file__).parent / "cluster.env"}


class ClusterConfig(CoreConfig):
    """Cluster-scoped Config.

    This wraps the core Config to always include ClusterSettings by default,
    so you can simply do:

        from mindtrace.cluster.config import ClusterConfig
        cfg = ClusterConfig()

    You can still pass extra overrides; they will be applied on top of cluster defaults.
    """

    def __init__(self, extra_settings: SettingsLike = None):
        if extra_settings is None:
            extras = [ClusterSettings()]
        elif isinstance(extra_settings, list):
            extras = [ClusterSettings()] + extra_settings
        else:
            extras = [ClusterSettings(), extra_settings]
        super().__init__(extra_settings=extras)


class Cluster(Mindtrace):
    def __init__(self, config_override: SettingsLike = None):
        self.config = ClusterConfig(config_override)


if __name__ == "__main__":
    cluster = Cluster()
    print("Core Settings", cluster.config.MINDTRACE_DIR_PATHS.REGISTRY_DIR)
    print("Cluster Settings from Cluster instance", cluster.config.MINDTRACE_CLUSTER.DEFAULT_REDIS_URL)
    print("Cluster Settings from Cluster instance", cluster.config.MINDTRACE_CLUSTER.MINIO_ENDPOINT)
    print("Cluster Settings from Cluster instance", cluster.config.MINDTRACE_CLUSTER.MINIO_ACCESS_KEY)
    print("Cluster Settings from Cluster instance", cluster.config.MINDTRACE_CLUSTER.MINIO_SECRET_KEY)
    print("Cluster Settings from Cluster instance", cluster.config.MINDTRACE_CLUSTER.MINIO_BUCKET)
    clusterconfig = ClusterConfig()
    print("Cluster Settings from ClusterConfig instance", clusterconfig.MINDTRACE_CLUSTER.DEFAULT_REDIS_URL)
    print("Cluster Settings from ClusterConfig instance", clusterconfig.MINDTRACE_CLUSTER.MINIO_ENDPOINT)
    print("Cluster Settings from ClusterConfig instance", clusterconfig.MINDTRACE_CLUSTER.MINIO_ACCESS_KEY)
    print("Cluster Settings from ClusterConfig instance", clusterconfig.MINDTRACE_CLUSTER.MINIO_SECRET_KEY)
    print("Cluster Settings from ClusterConfig instance", clusterconfig.MINDTRACE_CLUSTER.MINIO_BUCKET)
