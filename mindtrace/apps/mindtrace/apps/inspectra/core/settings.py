from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration for the Inspectra service.

    Similar role to HorizonSettings + get_horizon_config:
    - Strongly-typed settings
    - Defaults for local dev
    - Environment overrides via .env or real env vars
    """

    # =========================
    # General
    # =========================
    environment: str = Field(default="development", alias="ENVIRONMENT")
    api_port: int = Field(default=8000, alias="API_PORT")

    # =========================
    # Service metadata
    # =========================
    service_name: str = Field(default="inspectra", alias="SERVICE_NAME")
    service_description: str = Field(
        default="Inspectra Platform",
        alias="SERVICE_DESCRIPTION",
    )
    service_version: str = Field(default="1.0.0", alias="SERVICE_VERSION")
    service_author: str = Field(default="Inspectra", alias="SERVICE_AUTHOR")
    service_author_email: str = Field(
        default="inspectra@inspectra.com",
        alias="SERVICE_AUTHOR_EMAIL",
    )
    # This is the *public* URL we advertise in /config,
    # not necessarily the bind URL (we bind using API_PORT).
    service_url: str = Field(
        default="https://inspectra.com",
        alias="SERVICE_URL",
    )

    # =========================
    # JWT / Auth
    # =========================
    jwt_secret: str = Field(
        default="change_me_super_secret",
        alias="JWT_SECRET",
    )
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expires_in: int = Field(default=86400, alias="JWT_EXPIRES_IN")

    # =========================
    # MongoDB
    # =========================
    mongo_uri: str = Field(
        default=(
            "mongodb://inspectra_root:inspectra_root_password@mongo:27017/"
            "inspectra?authSource=admin"
        ),
        alias="MONGO_URI",
    )
    mongo_db_name: str = Field(default="inspectra", alias="MONGO_DB_NAME")

    # Pydantic v2 settings config
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()