"""Environment-backed settings for the VISO PRO API."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or a local .env."""

    model_config = SettingsConfigDict(
        env_prefix="VISO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "VISO PRO API"
    environment: str = "development"
    database_url: str | None = None
    auth_token_secret: SecretStr | None = None
    auth_token_ttl_minutes: int = Field(default=30, ge=5, le=1440)
    storage_provider: str = "cloudinary"
    cloudinary_cloud_name: str | None = Field(default=None, validation_alias="CLOUDINARY_CLOUD_NAME")
    cloudinary_api_key: str | None = Field(default=None, validation_alias="CLOUDINARY_API_KEY")
    cloudinary_api_secret: SecretStr | None = Field(default=None, validation_alias="CLOUDINARY_API_SECRET")
    s3_bucket: str | None = None
    s3_region: str = "us-east-1"
    s3_endpoint_url: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: SecretStr | None = None
    # AWS Academy Learner Lab credentials expire and require this session token.
    s3_session_token: SecretStr | None = None
    s3_presigned_url_ttl_seconds: int = Field(default=300, ge=60, le=3600)
    cors_origins: str = (
        "https://viso-pro.vercel.app,"
        "http://localhost:5500,http://127.0.0.1:5500,"
        "http://localhost:5173,http://127.0.0.1:5173"
    )

    @property
    def allowed_origins(self) -> list[str]:
        """Return configured browser origins as a clean list for FastAPI CORS."""

        return [
            origin.strip().rstrip("/")
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    """Cache settings so the API uses one consistent configuration per process."""

    return Settings()
