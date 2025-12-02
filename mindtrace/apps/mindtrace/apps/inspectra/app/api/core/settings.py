from pydantic import BaseSettings, Field

class Settings(BaseSettings):
    # General
    environment: str = Field(alias="ENVIRONMENT")
    api_port: int = Field(alias="API_PORT")

    # Service metadata
    service_name: str = Field(alias="SERVICE_NAME")
    service_description: str = Field(alias="SERVICE_DESCRIPTION")
    service_version: str = Field(alias="SERVICE_VERSION")
    service_author: str = Field(alias="SERVICE_AUTHOR")
    service_author_email: str = Field(alias="SERVICE_AUTHOR_EMAIL")
    service_url: str = Field(alias="SERVICE_URL")

    # JWT
    jwt_secret: str = Field(alias="JWT_SECRET")
    jwt_algorithm: str = Field(alias="JWT_ALGORITHM")
    jwt_expires_in: int = Field(alias="JWT_EXPIRES_IN")

    # MongoDB
    mongo_uri: str = Field(alias="MONGO_URI")
    mongo_db_name: str = Field(alias="MONGO_DB_NAME")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
