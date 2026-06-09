from pathlib import Path

from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings

from mindtrace.core import Mindtrace
from mindtrace.core.config import Config


class MINDTRACE_CLUSTER(BaseModel):
    DEFAULT_REDIS_URL: str
    MINIO_HOST: str
    MINIO_PORT: int
    MINIO_ACCESS_KEY: SecretStr
    MINIO_SECRET_KEY: SecretStr
    MINIO_BUCKET: str


class ClusterSettings(BaseSettings):
    MINDTRACE_CLUSTER: MINDTRACE_CLUSTER
    model_config = {"env_nested_delimiter": "__", "env_file": Path(__file__).parent / "cluster.env"}


class Cluster(Mindtrace):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)


if __name__ == "__main__":
    cluster = Cluster()
    print("Core Settings", cluster.config.MINDTRACE_DIR_PATHS.REGISTRY_DIR)
    config = Config()
    print("Config", config.MINDTRACE_DIR_PATHS.REGISTRY_DIR)
