from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    MONGO_URI: str
    DB_NAME: str
    SECRET_KEY: str
    GCP_BUCKET_NAME: str
    GCP_CREDENTIALS_PATH: str

    class Config:
        env_file = ".env"

settings = Settings() 