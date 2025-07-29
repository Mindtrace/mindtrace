from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    MONGO_URI: str = "mongodb://localhost:27017"
    DB_NAME: str = "mydb"
    SECRET_KEY: str = ""
    GCP_BUCKET_NAME: str = ""
    GCP_CREDENTIALS_PATH: str = ""

    MODEL_SERVER_URL: str = ""

    class Config:
        env_file = ".env"

settings = Settings() 