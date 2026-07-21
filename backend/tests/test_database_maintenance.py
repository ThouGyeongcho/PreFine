import sqlite3
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import pytest

import backend.app.database_maintenance as maintenance
from backend.app.database_maintenance import (
    MaintenanceError,
    backup_database,
    restore_database,
)


def write_value(path: Path, value: str) -> None:
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS sample (value TEXT NOT NULL)")
        connection.execute("DELETE FROM sample")
        connection.execute("INSERT INTO sample (value) VALUES (?)", (value,))
        connection.commit()


def read_value(path: Path) -> str:
    with closing(sqlite3.connect(path)) as connection:
        return str(connection.execute("SELECT value FROM sample").fetchone()[0])


def test_backup_creates_a_valid_timestamped_snapshot(tmp_path: Path) -> None:
    write_value(tmp_path / "prefine.db", "before")
    backup = backup_database(tmp_path)
    assert backup.parent == tmp_path / "backups"
    assert backup.name.startswith("prefine-") and backup.suffix == ".db"
    assert read_value(backup) == "before"
    assert not list(tmp_path.rglob("*.tmp"))


def test_restore_preserves_pre_restore_copy_and_replaces_atomically(tmp_path: Path) -> None:
    write_value(tmp_path / "prefine.db", "old-live")
    source = backup_database(tmp_path)
    write_value(source, "restored")
    write_value(tmp_path / "prefine.db", "new-live")
    safety = restore_database(tmp_path, source.name)
    assert read_value(tmp_path / "prefine.db") == "restored"
    assert safety.name.startswith("pre-restore-")
    assert read_value(safety) == "new-live"


@pytest.mark.parametrize("name", ["../prefine.db", "/tmp/prefine.db", "missing.db"])
def test_restore_rejects_escape_and_missing_sources(tmp_path: Path, name: str) -> None:
    write_value(tmp_path / "prefine.db", "live")
    with pytest.raises(MaintenanceError):
        restore_database(tmp_path, name)
    assert read_value(tmp_path / "prefine.db") == "live"


def test_corrupt_backup_never_replaces_live_database(tmp_path: Path) -> None:
    write_value(tmp_path / "prefine.db", "live")
    backups = tmp_path / "backups"
    backups.mkdir()
    (backups / "corrupt.db").write_bytes(b"not sqlite")
    with pytest.raises(MaintenanceError):
        restore_database(tmp_path, "corrupt.db")
    assert read_value(tmp_path / "prefine.db") == "live"
    assert not list(tmp_path.rglob("*.tmp"))


def test_copy_failure_removes_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_value(tmp_path / "prefine.db", "live")

    def deny_copy(_: Path, __: Path) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr(maintenance, "_copy_database", deny_copy)
    with pytest.raises(MaintenanceError):
        backup_database(tmp_path)
    assert read_value(tmp_path / "prefine.db") == "live"
    assert not list(tmp_path.rglob("*.tmp"))


def test_restore_replace_failure_keeps_live_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_value(tmp_path / "prefine.db", "backup-value")
    source = backup_database(tmp_path)
    write_value(tmp_path / "prefine.db", "live-value")
    real_replace = maintenance.os.replace
    calls = 0

    def fail_final_replace(source_path: Path, destination_path: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("replace denied")
        real_replace(source_path, destination_path)

    monkeypatch.setattr(maintenance.os, "replace", fail_final_replace)
    with pytest.raises(MaintenanceError):
        restore_database(tmp_path, source.name)
    assert read_value(tmp_path / "prefine.db") == "live-value"
    assert list((tmp_path / "backups").glob("pre-restore-*.db"))
    assert not list(tmp_path.rglob("*.tmp"))


def test_backup_cli_prints_snapshot_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    backup = tmp_path / "backups" / "prefine-20260722T000000Z.db"
    captured_data_dirs: list[Path] = []

    monkeypatch.setattr(
        maintenance, "get_settings", lambda: SimpleNamespace(data_dir=tmp_path)
    )

    def create_backup(data_dir: Path) -> Path:
        captured_data_dirs.append(data_dir)
        return backup

    monkeypatch.setattr(maintenance, "backup_database", create_backup)

    assert maintenance.main(["backup"]) == 0
    assert captured_data_dirs == [tmp_path]
    captured = capsys.readouterr()
    assert captured.out == f"{backup}\n"
    assert captured.err == ""


def test_backup_cli_reports_maintenance_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        maintenance, "get_settings", lambda: SimpleNamespace(data_dir=tmp_path)
    )

    def fail_backup(_: Path) -> Path:
        raise MaintenanceError("denied")

    monkeypatch.setattr(maintenance, "backup_database", fail_backup)

    assert maintenance.main(["backup"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "PreFine database maintenance error: denied\n"
