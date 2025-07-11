from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    MONGO_URI: str = "mongodb://localhost:27017"
    DB_NAME: str = "mydb"
    SECRET_KEY: str = "your-secret-key"
    GCP_BUCKET_NAME: str = "mtrix-datasets"
    GCP_CREDENTIALS_PATH: str = "/home/yasser/Desktop/datalake-sa-key.json"

    class Config:
        env_file = ".env"

settings = Settings() 