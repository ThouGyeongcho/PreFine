from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed application settings.

    Secret values remain wrapped in ``SecretStr`` so accidental string
    formatting cannot expose them in logs or API responses.
    """

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_ignore_empty=True,
        extra="ignore",
        populate_by_name=True,
    )

    admin_username: str = Field(alias="ADMIN_USERNAME", min_length=1)
    admin_password: SecretStr = Field(alias="ADMIN_PASSWORD", min_length=1)
    session_secret: SecretStr = Field(alias="SESSION_SECRET", min_length=32)
    data_dir: Path = Field(default=Path("/data"), alias="DATA_DIR")
    cookie_secure: bool = Field(default=False, alias="COOKIE_SECURE")
    timezone: str = Field(default="Asia/Shanghai", alias="TZ")
    smtp_host: str | None = Field(default=None, alias="SMTP_HOST")
    smtp_port: int | None = Field(default=None, alias="SMTP_PORT", ge=1, le=65535)
    smtp_username: str | None = Field(default=None, alias="SMTP_USERNAME")
    smtp_password: SecretStr | None = Field(default=None, alias="SMTP_PASSWORD")
    smtp_from: str | None = Field(default=None, alias="SMTP_FROM")
    reminder_to_email: str | None = Field(default=None, alias="REMINDER_TO_EMAIL")
    smtp_use_tls: bool = Field(default=False, alias="SMTP_USE_TLS")
    smtp_starttls: bool = Field(default=False, alias="SMTP_STARTTLS")

    @model_validator(mode="after")
    def mutually_exclusive_smtp_security(self) -> "Settings":
        if self.smtp_use_tls and self.smtp_starttls:
            raise ValueError("SMTP_USE_TLS 和 SMTP_STARTTLS 不能同时启用")
        return self

    @property
    def database_path(self) -> Path:
        return self.data_dir / "finance-toolkit.db"

    @property
    def email_configured(self) -> bool:
        return all((self.smtp_host, self.smtp_port, self.smtp_from, self.reminder_to_email))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
