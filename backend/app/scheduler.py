import asyncio
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from backend.app.calendar import CalendarUnavailableError
from backend.app.db import Database
from backend.app.models import CalendarSyncState
from backend.app.reminders import ReminderRunResult
from backend.app.tax_profile import TaxToolSettings
from backend.app.tax_source import YearMonth


class CalendarRefresher(Protocol):
    async def sync_month(self, region_code: str, month: YearMonth) -> object: ...


class TaxProfileReader(Protocol):
    def get_settings(self) -> TaxToolSettings: ...


class ReminderChecker(Protocol):
    async def check_due(self, now: datetime | None = None) -> ReminderRunResult: ...


class SchedulerManager:
    def __init__(
        self,
        database: Database,
        calendar: CalendarRefresher,
        tax_profile: TaxProfileReader,
        reminders: ReminderChecker,
        *,
        timezone: str = "Asia/Shanghai",
        now: Callable[[], datetime] | None = None,
        spawn: Callable[[Coroutine[Any, Any, Any]], Any] | None = None,
    ) -> None:
        self._database = database
        self._calendar = calendar
        self._tax_profile = tax_profile
        self._reminders = reminders
        self._timezone = ZoneInfo(timezone)
        self._now = now or (lambda: datetime.now(UTC))
        self._scheduler = AsyncIOScheduler(timezone=self._timezone)
        self._tasks: set[asyncio.Task[Any]] = set()
        self._spawn = spawn or self._spawn_background

    @property
    def status(self) -> str:
        return "running" if self._scheduler.running else "stopped"

    @property
    def jobs(self) -> list[Any]:
        return self._scheduler.get_jobs()

    def start(self) -> None:
        if self._scheduler.running:
            return
        self._scheduler.add_job(
            self.refresh_priority_months,
            CronTrigger(hour=8, minute=0, timezone=self._timezone),
            id="calendar-refresh",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        self._scheduler.add_job(
            self.run_reminder_check,
            CronTrigger(hour="9-18", minute=0, timezone=self._timezone),
            id="reminder-check",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        self._scheduler.start()
        local_now = self._local_time(self._now())
        if 9 <= local_now.hour <= 18:
            self._spawn(self._reminders.check_due(local_now))

    async def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            await asyncio.sleep(0)

    async def run_reminder_check(self) -> ReminderRunResult:
        return await self._reminders.check_due(self._local_time(self._now()))

    async def refresh_priority_months(self, now: datetime | None = None) -> None:
        local_now = self._local_time(now or self._now())
        settings = self._tax_profile.get_settings()
        targets: set[tuple[str, YearMonth]] = set()
        if settings.default_region_code is not None:
            current = YearMonth(local_now.year, local_now.month)
            targets.add((settings.default_region_code, current))
            targets.add((settings.default_region_code, _next_month(current)))

        cutoff = (local_now.astimezone(UTC) - timedelta(days=30)).replace(tzinfo=None)
        with self._database.session() as session:
            recent = session.scalars(
                select(CalendarSyncState).where(CalendarSyncState.last_accessed_at >= cutoff)
            ).all()
        for state in recent:
            try:
                targets.add((state.region_code, YearMonth.parse(state.cache_month)))
            except ValueError:
                continue

        for region_code, month in sorted(targets, key=lambda item: (item[0], item[1])):
            try:
                await self._calendar.sync_month(region_code, month)
            except CalendarUnavailableError:
                continue

    def _local_time(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(self._timezone)

    def _spawn_background(self, coroutine: Coroutine[Any, Any, Any]) -> None:
        task = asyncio.create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


def _next_month(month: YearMonth) -> YearMonth:
    if month.month == 12:
        return YearMonth(month.year + 1, 1)
    return YearMonth(month.year, month.month + 1)
