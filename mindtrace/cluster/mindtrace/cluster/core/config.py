from pydantic import SecretStr
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from pathlib import Path
from mindtrace.core.config import Config as CoreConfig, SettingsLike, CoreSettings


class MINDTRACE_CLUSTER(BaseModel):
    DEFAULT_REDIS_URL: str
    MINIO_ENDPOINT: str
    MINIO_ACCESS_KEY: SecretStr
    MINIO_SECRET_KEY: SecretStr
    MINIO_BUCKET: str 

class ClusterSettings(BaseSettings):
    MINDTRACE_CLUSTER: MINDTRACE_CLUSTER
    model_config = {
        "env_nested_delimiter": "__", 
        "env_file": Path(__file__).parent / "cluster.env"
    }


class Config(CoreConfig):
    """Cluster-scoped Config.

    This wraps the core Config to always include ClusterSettings by default,
    so you can simply do:

        from mindtrace.cluster.config import Config
        cfg = Config()

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
