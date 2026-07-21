from functools import lru_cache
from ipaddress import IPv4Address, IPv6Address, ip_address
from pathlib import Path

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

EXAMPLE_ADMIN_PASSWORD = "CHANGE_ME_ADMIN_PASSWORD"
EXAMPLE_SESSION_SECRET = "CHANGE_ME_SESSION_SECRET"


class Settings(BaseSettings):
    """Environment-backed application settings.

    Secret values remain wrapped in ``SecretStr`` so accidental string
    formatting cannot expose them in logs or API responses.
    """

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_ignore_empty=True,
        extra="ignore",
        hide_input_in_errors=True,
        populate_by_name=True,
    )

    admin_username: str = Field(alias="ADMIN_USERNAME", min_length=1)
    admin_password: SecretStr = Field(alias="ADMIN_PASSWORD", min_length=12)
    session_secret: SecretStr = Field(alias="SESSION_SECRET", min_length=32)
    data_dir: Path = Field(default=Path("/data"), alias="DATA_DIR")
    cookie_secure: bool = Field(default=False, alias="COOKIE_SECURE")
    trusted_proxy_ips: str = Field(default="", alias="TRUSTED_PROXY_IPS")
    timezone: str = Field(default="Asia/Shanghai", alias="TZ")
    smtp_host: str | None = Field(default=None, alias="SMTP_HOST")
    smtp_port: int | None = Field(default=None, alias="SMTP_PORT", ge=1, le=65535)
    smtp_username: str | None = Field(default=None, alias="SMTP_USERNAME")
    smtp_password: SecretStr | None = Field(default=None, alias="SMTP_PASSWORD")
    smtp_from: str | None = Field(default=None, alias="SMTP_FROM")
    reminder_to_email: str | None = Field(default=None, alias="REMINDER_TO_EMAIL")
    smtp_use_tls: bool = Field(default=False, alias="SMTP_USE_TLS")
    smtp_starttls: bool = Field(default=False, alias="SMTP_STARTTLS")

    @field_validator("admin_password", mode="before")
    @classmethod
    def reject_example_admin_password(cls, value: str | SecretStr) -> str | SecretStr:
        secret_value = (
            value.get_secret_value() if isinstance(value, SecretStr) else value
        )
        if len(secret_value) < 12:
            raise ValueError("ADMIN_PASSWORD must contain at least 12 characters")
        if secret_value == EXAMPLE_ADMIN_PASSWORD:
            raise ValueError("ADMIN_PASSWORD must not use the example value")
        return value

    @field_validator("session_secret", mode="before")
    @classmethod
    def reject_example_session_secret(cls, value: str | SecretStr) -> str | SecretStr:
        secret_value = (
            value.get_secret_value() if isinstance(value, SecretStr) else value
        )
        if len(secret_value) < 32:
            raise ValueError("SESSION_SECRET must contain at least 32 characters")
        if secret_value == EXAMPLE_SESSION_SECRET:
            raise ValueError("SESSION_SECRET must not use the example value")
        return value

    @field_validator("trusted_proxy_ips")
    @classmethod
    def normalize_trusted_proxy_ips(cls, value: str) -> str:
        if value == "":
            return value
        parts = [part.strip() for part in value.split(",")]
        if any(part == "" for part in parts):
            raise ValueError("TRUSTED_PROXY_IPS must contain exact IP addresses")
        try:
            return ",".join(str(ip_address(part)) for part in parts)
        except ValueError as error:
            raise ValueError(
                "TRUSTED_PROXY_IPS must contain exact IP addresses"
            ) from error

    @model_validator(mode="after")
    def mutually_exclusive_smtp_security(self) -> "Settings":
        if self.smtp_use_tls and self.smtp_starttls:
            raise ValueError("SMTP_USE_TLS 和 SMTP_STARTTLS 不能同时启用")
        return self

    @property
    def database_path(self) -> Path:
        return self.data_dir / "prefine.db"

    @property
    def trusted_proxy_addresses(self) -> frozenset[IPv4Address | IPv6Address]:
        if not self.trusted_proxy_ips:
            return frozenset()
        return frozenset(ip_address(part) for part in self.trusted_proxy_ips.split(","))

    @property
    def email_configured(self) -> bool:
        return all((self.smtp_host, self.smtp_port, self.smtp_from, self.reminder_to_email))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
