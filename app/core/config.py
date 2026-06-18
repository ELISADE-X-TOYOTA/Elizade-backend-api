from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://elizade:elizade@localhost:5432/elizade_connect"
    jwt_secret: str = "dev-secret"
    jwt_expire_minutes: int = 10080  # 7 days
    admin_phone_normalized: str = "8107891549"
    otp_expire_minutes: int = 10
    otp_length: int = 6
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
