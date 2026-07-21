from __future__ import annotations

import pytest

from backend.app.container_identity import ContainerIdentity, main, parse_positive_id


def test_container_identity_defaults_to_uid_and_gid_1000(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PUID", raising=False)
    monkeypatch.delenv("PGID", raising=False)

    assert ContainerIdentity.from_environment() == ContainerIdentity(uid=1000, gid=1000)


@pytest.mark.parametrize("raw", ["", "0", "-1", "1.5", "abc", "１２３"])
def test_container_identity_rejects_invalid_values(raw: str) -> None:
    with pytest.raises(ValueError, match="positive ASCII decimal integer"):
        parse_positive_id("PUID", raw)


def test_container_identity_accepts_positive_ascii_decimal_values() -> None:
    assert parse_positive_id("PGID", "1001") == 1001


def test_container_identity_cli_prints_identity(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("PUID", "1002")
    monkeypatch.setenv("PGID", "1003")

    assert main() == 0
    assert capsys.readouterr().out == "1002:1003\n"


def test_container_identity_cli_reports_invalid_ids(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("PUID", "0")

    assert main() == 64
    assert capsys.readouterr().err == (
        "PreFine startup error: PUID must be a positive ASCII decimal integer\n"
    )
