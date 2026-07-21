from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.config import Settings


def valid_values(tmp_path: Path) -> dict[str, object]:
    return {
        "ADMIN_USERNAME": "admin",
        "ADMIN_PASSWORD": "correct horse battery staple",
        "SESSION_SECRET": "0123456789abcdef0123456789abcdef",
        "DATA_DIR": tmp_path,
    }


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("ADMIN_PASSWORD", "short"),
        ("ADMIN_PASSWORD", "CHANGE_ME_ADMIN_PASSWORD"),
        ("SESSION_SECRET", "too-short"),
        ("SESSION_SECRET", "CHANGE_ME_SESSION_SECRET"),
    ],
)
def test_rejects_unsafe_required_credentials(
    tmp_path: Path, name: str, value: str
) -> None:
    values = valid_values(tmp_path)
    values[name] = value
    with pytest.raises(ValidationError) as caught:
        Settings(**values)
    assert name in str(caught.value)
    assert value not in str(caught.value)


def test_normalizes_exact_trusted_proxy_addresses(tmp_path: Path) -> None:
    settings = Settings(
        **valid_values(tmp_path),
        TRUSTED_PROXY_IPS=" 127.0.0.1,2001:db8::1 ",
    )
    assert {str(value) for value in settings.trusted_proxy_addresses} == {
        "127.0.0.1",
        "2001:db8::1",
    }


@pytest.mark.parametrize("value", ["proxy.local", "127.0.0.1,", "127.0.0.1,not-ip"])
def test_rejects_invalid_trusted_proxy_configuration(
    tmp_path: Path, value: str
) -> None:
    with pytest.raises(ValidationError):
        Settings(**valid_values(tmp_path), TRUSTED_PROXY_IPS=value)
