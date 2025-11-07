import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    MONGO_URI: str
    DB_NAME: str
    SECRET_KEY: str
    JWT_SECRET: str
    GCP_BUCKET_NAME: str
    GCP_CREDENTIALS_PATH: str

    model_config = SettingsConfigDict(env_file=".env.dev", env_file_encoding="utf-8", extra="ignore")


ENV = os.getenv("ENV", "dev")  # dev/prod
try:
    config = Settings(_env_file=f".env.{ENV}", _env_file_encoding="utf-8")
except Exception as e:
    raise Exception(f"Error loading config, check your env file contains fields.: {e}")
