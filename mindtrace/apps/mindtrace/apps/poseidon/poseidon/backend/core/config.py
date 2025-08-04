from pydantic_settings import BaseSettings, SettingsConfigDict
import os


class Settings(BaseSettings):
    MONGO_URI: str
    DB_NAME: str
    SECRET_KEY: str
    GCP_BUCKET_NAME: str
    GCP_CREDENTIALS_PATH: str
    MODEL_SERVER_URL: str

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


ENV = os.getenv("ENV", "dev")  # dev/prod
settings = Settings(_env_file=f".env.{ENV}", _env_file_encoding="utf-8")
