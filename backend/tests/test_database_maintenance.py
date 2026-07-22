import sqlite3
import subprocess
import sys
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


def test_restore_quarantines_crashed_wal_sidecars_before_replacing_live_database(
    tmp_path: Path,
) -> None:
    live = tmp_path / "prefine.db"
    write_value(live, "old-live")
    source = backup_database(tmp_path)
    write_value(source, "restored")

    crash_writer = "\n".join(
        (
            "import os, sqlite3, sys",
            "connection = sqlite3.connect(sys.argv[1])",
            "connection.execute('PRAGMA journal_mode=WAL')",
            "connection.execute('PRAGMA wal_autocheckpoint=0')",
            "connection.execute('UPDATE sample SET value = ?', ('stale-wal',))",
            "connection.commit()",
            "os._exit(0)",
        )
    )
    subprocess.run(
        [sys.executable, "-c", crash_writer, str(live)],
        check=True,
    )
    sidecars = [Path(f"{live}-wal"), Path(f"{live}-shm")]
    assert all(sidecar.is_file() for sidecar in sidecars)

    restore_database(tmp_path, source.name)

    assert read_value(live) == "restored"
    assert not any(sidecar.exists() for sidecar in sidecars)
    assert not list(tmp_path.glob(".prefine-sidecar-*.quarantine"))


def test_restore_replace_failure_restores_quarantined_wal_sidecars(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live = tmp_path / "prefine.db"
    write_value(live, "old-live")
    source = backup_database(tmp_path)
    write_value(source, "restored")
    crash_writer = "\n".join(
        (
            "import os, sqlite3, sys",
            "connection = sqlite3.connect(sys.argv[1])",
            "connection.execute('PRAGMA journal_mode=WAL')",
            "connection.execute('PRAGMA wal_autocheckpoint=0')",
            "connection.execute('UPDATE sample SET value = ?', ('stale-wal',))",
            "connection.commit()",
            "os._exit(0)",
        )
    )
    subprocess.run([sys.executable, "-c", crash_writer, str(live)], check=True)
    sidecars = [Path(f"{live}-wal"), Path(f"{live}-shm")]
    real_replace = maintenance.os.replace
    replacements: list[tuple[Path, Path]] = []

    def fail_live_replace(source_path: Path, destination_path: Path) -> None:
        replacements.append((Path(source_path), Path(destination_path)))
        if destination_path == live and source_path.name.startswith(".prefine-restore-"):
            raise OSError("replace denied")
        real_replace(source_path, destination_path)

    monkeypatch.setattr(maintenance.os, "replace", fail_live_replace)

    with pytest.raises(MaintenanceError, match="Could not replace live"):
        restore_database(tmp_path, source.name)

    assert all(sidecar.is_file() for sidecar in sidecars)
    assert any(destination.suffix == ".quarantine" for _, destination in replacements)
    assert all(
        any(
            source_path.suffix == ".quarantine" and destination == sidecar
            for source_path, destination in replacements
        )
        for sidecar in sidecars
    )
    assert not list(tmp_path.glob(".prefine-sidecar-*.quarantine"))
    assert read_value(live) == "stale-wal"


def _symlink_directory_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except (NotImplementedError, OSError) as symlink_error:
        if sys.platform != "win32":
            pytest.skip(f"directory symlinks are unavailable: {symlink_error}")
    junction = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if junction.returncode != 0:
        pytest.skip(f"directory symlinks and junctions are unavailable: {junction.stderr.strip()}")


def test_backup_rejects_symlinked_backup_directory_escape(tmp_path: Path) -> None:
    write_value(tmp_path / "prefine.db", "live")
    outside = tmp_path.parent / f"{tmp_path.name}-outside-backups"
    outside.mkdir()
    _symlink_directory_or_skip(tmp_path / "backups", outside)

    with pytest.raises(MaintenanceError, match="Backup directory"):
        backup_database(tmp_path)

    assert not list(outside.iterdir())


def test_restore_rejects_symlinked_backup_directory_escape(tmp_path: Path) -> None:
    write_value(tmp_path / "prefine.db", "live")
    outside = tmp_path.parent / f"{tmp_path.name}-outside-backups"
    outside.mkdir()
    write_value(outside / "outside.db", "outside")
    _symlink_directory_or_skip(tmp_path / "backups", outside)

    with pytest.raises(MaintenanceError, match="Backup directory"):
        restore_database(tmp_path, "outside.db")

    assert read_value(tmp_path / "prefine.db") == "live"


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

    monkeypatch.setattr(maintenance, "get_settings", lambda: SimpleNamespace(data_dir=tmp_path))

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
    monkeypatch.setattr(maintenance, "get_settings", lambda: SimpleNamespace(data_dir=tmp_path))

    def fail_backup(_: Path) -> Path:
        raise MaintenanceError("denied")

    monkeypatch.setattr(maintenance, "backup_database", fail_backup)

    assert maintenance.main(["backup"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "PreFine database maintenance error: denied\n"
