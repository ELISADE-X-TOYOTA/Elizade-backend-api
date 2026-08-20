from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://elizade:elizade@localhost:5432/elizade_connect"
    jwt_secret: str = "dev-secret"
    jwt_expire_minutes: int = 10080  # 7 days
    admin_email: str = "divinewilson766@gmail.com"
    otp_expire_minutes: int = 10
    otp_length: int = 6
    cors_origins: str = "http://localhost:5173"

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "noreply@meristemng.com"
    smtp_use_tls: bool = True

    # Shown in transactional email (footer / support links).
    support_email: str = "support@elizade.com"
    support_phone: str = "+234 700 354 9233"
    support_url: str = "https://elizade.com/contact"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_username and self.smtp_password)


@lru_cache
def get_settings() -> Settings:
    return Settings()
