from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker


class Database:
    """Owns the SQLite engine and short-lived SQLAlchemy sessions."""

    def __init__(self, database_path: Path) -> None:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self.path = database_path
        self.engine = create_engine(
            f"sqlite+pysqlite:///{database_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        event.listen(self.engine, "connect", self._configure_sqlite)
        self._session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
        )

    @staticmethod
    def _configure_sqlite(dbapi_connection: Any, _: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    @contextmanager
    def session(self) -> Iterator[Session]:
        with self._session_factory() as session:
            yield session

    def check(self) -> bool:
        try:
            with self.engine.connect() as connection:
                transaction = connection.begin()
                connection.execute(text("SELECT 1"))
                connection.execute(
                    text(
                        "INSERT INTO tool_settings (tool_key, value, updated_at) "
                        "VALUES ('__health_check__', '{}', CURRENT_TIMESTAMP) "
                        "ON CONFLICT(tool_key) DO UPDATE SET updated_at = excluded.updated_at"
                    )
                )
                transaction.rollback()
            return True
        except SQLAlchemyError:
            return False

    def dispose(self) -> None:
        self.engine.dispose()


def create_database(database_path: Path) -> Database:
    return Database(database_path)


def get_session(database: Database) -> Iterator[Session]:
    with database.session() as session:
        yield session
