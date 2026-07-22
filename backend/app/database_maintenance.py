from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import tempfile
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from backend.app.config import get_settings


class MaintenanceError(RuntimeError):
    pass


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _temporary_path(directory: Path, prefix: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=prefix, suffix=".tmp", dir=directory, delete=False
    ) as handle:
        return Path(handle.name)


def _read_only_uri(path: Path) -> str:
    return f"{path.resolve().as_uri()}?mode=ro"


def _integrity_check(path: Path) -> None:
    try:
        with closing(sqlite3.connect(_read_only_uri(path), uri=True)) as connection:
            rows = connection.execute("PRAGMA integrity_check").fetchall()
    except sqlite3.Error as error:
        raise MaintenanceError(f"SQLite integrity check failed for {path.name}") from error
    if rows != [("ok",)]:
        raise MaintenanceError(f"SQLite integrity check failed for {path.name}")


def _copy_database(source: Path, destination: Path) -> None:
    try:
        with (
            closing(sqlite3.connect(_read_only_uri(source), uri=True)) as source_db,
            closing(sqlite3.connect(destination)) as destination_db,
        ):
            source_db.backup(destination_db)
            destination_db.commit()
    except (OSError, sqlite3.Error) as error:
        raise MaintenanceError(f"Could not copy SQLite database {source.name}") from error


def _final_path(directory: Path, prefix: str) -> Path:
    path = directory / f"{prefix}-{_timestamp()}.db"
    if path.exists():
        raise MaintenanceError(f"Backup already exists: {path.name}")
    return path


def _backup_directory(data_dir: Path) -> Path:
    data_root = data_dir.resolve()
    backup_dir = data_root / "backups"
    is_junction = getattr(backup_dir, "is_junction", lambda: False)
    if backup_dir.is_symlink() or is_junction():
        raise MaintenanceError("Backup directory must not be a symbolic link")
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise MaintenanceError("Could not create backup directory") from error
    if backup_dir.is_symlink() or is_junction() or not backup_dir.is_dir():
        raise MaintenanceError("Backup directory must be a regular directory")
    resolved = backup_dir.resolve()
    try:
        resolved.relative_to(data_root)
    except ValueError as error:
        raise MaintenanceError("Backup directory escaped the data directory") from error
    return resolved


def backup_database(data_dir: Path, prefix: str = "prefine") -> Path:
    source = data_dir / "prefine.db"
    if not source.is_file() or source.is_symlink():
        raise MaintenanceError("Live database /data/prefine.db is missing")
    backup_dir = _backup_directory(data_dir)
    temporary = _temporary_path(backup_dir, f".{prefix}-")
    try:
        _copy_database(source, temporary)
        _integrity_check(temporary)
        final = _final_path(backup_dir, prefix)
        os.replace(temporary, final)
        return final
    except (MaintenanceError, OSError) as error:
        temporary.unlink(missing_ok=True)
        if isinstance(error, MaintenanceError):
            raise
        raise MaintenanceError("Could not finalize SQLite backup") from error


def _resolve_backup(data_dir: Path, backup_name: str) -> Path:
    if Path(backup_name).name != backup_name:
        raise MaintenanceError("Restore source must be a backup file name")
    backup_dir = _backup_directory(data_dir)
    candidate = backup_dir / backup_name
    if candidate.is_symlink() or not candidate.is_file():
        raise MaintenanceError(f"Backup does not exist: {backup_name}")
    resolved = candidate.resolve()
    if resolved.parent != backup_dir:
        raise MaintenanceError("Restore source escaped /data/backups")
    return resolved


def _quarantine_sidecars(live: Path) -> list[tuple[Path, Path]]:
    quarantined: list[tuple[Path, Path]] = []
    try:
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{live}{suffix}")
            if not os.path.lexists(sidecar):
                continue
            quarantine = live.parent / (f".prefine-sidecar-{uuid.uuid4().hex}.quarantine")
            os.replace(sidecar, quarantine)
            quarantined.append((sidecar, quarantine))
    except OSError as error:
        try:
            _restore_quarantined_sidecars(quarantined)
        except MaintenanceError as rollback_error:
            raise MaintenanceError(
                "Could not quarantine SQLite sidecars and rollback failed"
            ) from rollback_error
        raise MaintenanceError("Could not quarantine SQLite sidecars") from error
    return quarantined


def _restore_quarantined_sidecars(
    quarantined: list[tuple[Path, Path]],
) -> None:
    try:
        for sidecar, quarantine in reversed(quarantined):
            os.replace(quarantine, sidecar)
    except OSError as error:
        raise MaintenanceError("Could not restore SQLite sidecars") from error


def _discard_quarantined_sidecars(quarantined: list[tuple[Path, Path]]) -> None:
    try:
        for _, quarantine in quarantined:
            quarantine.unlink(missing_ok=True)
    except OSError as error:
        raise MaintenanceError("Could not remove quarantined SQLite sidecars") from error


def restore_database(data_dir: Path, backup_name: str) -> Path:
    source = _resolve_backup(data_dir, backup_name)
    _integrity_check(source)
    safety = backup_database(data_dir, prefix="pre-restore")
    live = data_dir / "prefine.db"
    temporary = _temporary_path(data_dir, ".prefine-restore-")
    try:
        _copy_database(source, temporary)
        _integrity_check(temporary)
        quarantined = _quarantine_sidecars(live)
        try:
            os.replace(temporary, live)
        except OSError as error:
            try:
                _restore_quarantined_sidecars(quarantined)
            except MaintenanceError as rollback_error:
                raise MaintenanceError(
                    "Could not replace live SQLite database and sidecar rollback failed"
                ) from rollback_error
            raise MaintenanceError("Could not replace live SQLite database") from error
        _discard_quarantined_sidecars(quarantined)
        return safety
    except (MaintenanceError, OSError) as error:
        temporary.unlink(missing_ok=True)
        if isinstance(error, MaintenanceError):
            raise
        raise MaintenanceError("Could not replace live SQLite database") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="prefine-database")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("backup")
    restore = subparsers.add_parser("restore")
    restore.add_argument("backup_name")
    args = parser.parse_args(argv)
    data_dir = get_settings().data_dir
    try:
        if args.command == "backup":
            result = backup_database(data_dir)
            print(result)
        else:
            result = restore_database(data_dir, args.backup_name)
            print(f"pre-restore backup: {result}")
    except MaintenanceError as error:
        print(f"PreFine database maintenance error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
