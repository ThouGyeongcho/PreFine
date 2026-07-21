from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app import __version__
from backend.app.api import build_api_router
from backend.app.auth import AuthService
from backend.app.calendar import CalendarService, CalendarSource
from backend.app.config import Settings, get_settings
from backend.app.db import Database
from backend.app.errors import install_error_handlers
from backend.app.reminders import EmailSender, ReminderService, SmtpEmailSender
from backend.app.scheduler import SchedulerManager
from backend.app.tax_profile import TaxProfileService, load_catalog
from backend.app.tax_source import TaxSourceClient, load_seed_regions


def create_app(
    settings: Settings | None = None,
    *,
    start_scheduler: bool = True,
    auth_now: Callable[[], datetime] | None = None,
    tax_source: CalendarSource | None = None,
    calendar_now: Callable[[], datetime] | None = None,
    email_sender: EmailSender | None = None,
    static_dir: Path | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        _run_migrations(resolved_settings.database_path)
        database = Database(resolved_settings.database_path)
        app.state.database = database
        app.state.auth_service = AuthService(resolved_settings, now=auth_now)
        source = tax_source or TaxSourceClient()
        app.state.regions = load_seed_regions()
        app.state.tax_profile_service = TaxProfileService(
            database,
            load_catalog(),
            {region.code for region in app.state.regions},
        )
        app.state.tax_profile_service.seed_catalog()
        app.state.calendar_service = CalendarService(
            database,
            source,
            now=calendar_now,
        )
        app.state.reminder_service = ReminderService(
            database,
            app.state.calendar_service,
            app.state.tax_profile_service,
            resolved_settings,
            email_sender or SmtpEmailSender(resolved_settings),
        )
        app.state.scheduler_manager = SchedulerManager(
            database,
            app.state.calendar_service,
            app.state.tax_profile_service,
            app.state.reminder_service,
            timezone=resolved_settings.timezone,
        )
        if start_scheduler:
            app.state.scheduler_manager.start()
        try:
            yield
        finally:
            await app.state.scheduler_manager.shutdown()
            if tax_source is None:
                await source.aclose()
            database.dispose()

    app = FastAPI(title="PreFine", version=__version__, lifespan=lifespan)
    app.state.settings = resolved_settings
    install_error_handlers(app)
    app.include_router(build_api_router())

    @app.get("/api/health")
    def health(request: Request, response: Response) -> dict[str, str]:
        database_status = "ok" if request.app.state.database.check() else "unavailable"
        scheduler_status = request.app.state.scheduler_manager.status
        scheduler_healthy = not start_scheduler or scheduler_status == "running"
        status = "ok" if database_status == "ok" and scheduler_healthy else "error"
        if status == "error":
            response.status_code = 503
        return {
            "status": status,
            "database": database_status,
            "scheduler": scheduler_status,
            "version": __version__,
        }

    frontend_dist = static_dir or Path(__file__).resolve().parents[2] / "frontend" / "dist"
    frontend_index = frontend_dist / "index.html"
    frontend_assets = frontend_dist / "assets"
    if frontend_index.is_file():
        if frontend_assets.is_dir():
            app.mount("/assets", StaticFiles(directory=frontend_assets), name="frontend-assets")

        @app.get("/{path:path}", include_in_schema=False)
        def frontend(path: str) -> FileResponse:
            if path == "api" or path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not Found")
            return FileResponse(frontend_index)

    return app


def _run_migrations(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    alembic_path = Path(__file__).resolve().parents[1] / "alembic.ini"
    config = Config(str(alembic_path))
    config.set_main_option(
        "sqlalchemy.url",
        f"sqlite+pysqlite:///{database_path.as_posix()}",
    )
    command.upgrade(config, "head")
