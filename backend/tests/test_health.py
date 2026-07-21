import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.config import Settings
from backend.app.main import create_app


def make_settings(data_dir: Path) -> Settings:
    return Settings(
        ADMIN_USERNAME="admin",
        ADMIN_PASSWORD="correct horse battery staple",
        SESSION_SECRET="0123456789abcdef0123456789abcdef",
        DATA_DIR=data_dir,
    )


def test_session_secret_requires_at_least_32_characters(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        Settings(
            ADMIN_USERNAME="admin",
            ADMIN_PASSWORD="secret",
            SESSION_SECRET="short",
            DATA_DIR=tmp_path,
        )


def test_empty_optional_environment_values_are_ignored(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SMTP_PORT", "")

    settings = make_settings(tmp_path)

    assert settings.smtp_port is None


def test_health_does_not_require_authentication(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), start_scheduler=False)

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "scheduler": "stopped",
        "version": "0.1.0",
    }


def test_application_uses_exact_prefine_title(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), start_scheduler=False)

    assert app.title == "PreFine"


def test_health_response_never_contains_configuration_values(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    app = create_app(settings, start_scheduler=False)

    with TestClient(app) as client:
        body = client.get("/api/health").text

    assert settings.admin_username not in body
    assert settings.admin_password.get_secret_value() not in body
    assert settings.session_secret.get_secret_value() not in body


def test_health_degrades_when_the_expected_scheduler_stops(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), start_scheduler=True)

    with TestClient(app) as client:
        running = client.get("/api/health")
        app.state.scheduler_manager._scheduler.shutdown(wait=False)
        stopped = client.get("/api/health")

    assert running.json()["status"] == "ok"
    assert running.json()["scheduler"] == "running"
    assert stopped.json()["status"] == "error"
    assert stopped.json()["scheduler"] == "stopped"
    assert stopped.status_code == 503


def test_startup_creates_the_approved_schema_and_sqlite_pragmas(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), start_scheduler=False)

    with TestClient(app):
        pass

    connection = sqlite3.connect(tmp_path / "prefine.db")
    table_names = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
    journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
    busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
    connection.close()

    assert table_names == {
        "alembic_version",
        "calendar_events",
        "calendar_sync_state",
        "tax_catalog_items",
        "tax_catalog_aliases",
        "tool_settings",
        "email_dispatches",
    }
    # Foreign keys are configured for application connections. The independent
    # sqlite3 connection starts with SQLite's default and validates the durable settings.
    assert foreign_keys == 0
    assert journal_mode == "wal"
    assert busy_timeout == 5000


def test_initial_alembic_migration_creates_the_approved_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "migrated.db"
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database_path.as_posix()}")

    command.upgrade(config, "head")

    connection = sqlite3.connect(database_path)
    table_names = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    connection.close()
    assert table_names == {
        "alembic_version",
        "calendar_events",
        "calendar_sync_state",
        "tax_catalog_items",
        "tax_catalog_aliases",
        "tool_settings",
        "email_dispatches",
    }
