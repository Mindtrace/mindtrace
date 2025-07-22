from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    MONGO_URI: str = "mongodb://localhost:27017"
    DB_NAME: str = "mydb"
    SECRET_KEY: str = "your-secret-key"
    GCP_BUCKET_NAME: str = "paz-test-bucket"
    GCP_CREDENTIALS_PATH: str = "/home/uzair/mindtrace/mindtrace/ui/mindtrace/ui/poseidon/poseidon/backend/core/paz-portal.json"

    class Config:
        env_file = ".env"

settings = Settings() 