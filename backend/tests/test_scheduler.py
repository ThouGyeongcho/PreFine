from collections.abc import Coroutine
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from backend.app.db import Database
from backend.app.models import Base, CalendarSyncState
from backend.app.reminders import ReminderRunResult
from backend.app.scheduler import SchedulerManager
from backend.app.tax_profile import TaxToolSettings
from backend.app.tax_source import YearMonth

BEIJING = timezone(timedelta(hours=8))


class FakeCalendar:
    def __init__(self) -> None:
        self.calls: list[tuple[str, YearMonth]] = []

    async def sync_month(self, region_code: str, month: YearMonth) -> object:
        self.calls.append((region_code, month))
        return object()


class FakeTaxProfile:
    def __init__(self, region_code: str | None = "111000000") -> None:
        self.settings = TaxToolSettings(default_region_code=region_code)

    def get_settings(self) -> TaxToolSettings:
        return self.settings


class FakeReminders:
    def __init__(self) -> None:
        self.calls: list[datetime | None] = []

    async def check_due(self, now: datetime | None = None) -> ReminderRunResult:
        self.calls.append(now)
        return ReminderRunResult()


@pytest.fixture
def database(tmp_path: Path) -> Database:
    value = Database(tmp_path / "scheduler.db")
    Base.metadata.create_all(value.engine)
    try:
        yield value
    finally:
        value.dispose()


@pytest.mark.asyncio
async def test_scheduler_registers_the_approved_cron_windows(database: Database) -> None:
    manager = SchedulerManager(
        database,
        FakeCalendar(),
        FakeTaxProfile(),
        FakeReminders(),
        now=lambda: datetime(2026, 7, 21, 7, tzinfo=BEIJING),
    )

    manager.start()
    try:
        jobs = {job.id: str(job.trigger) for job in manager.jobs}
        assert manager.status == "running"
        assert "hour='8'" in jobs["calendar-refresh"]
        assert "minute='0'" in jobs["calendar-refresh"]
        assert "hour='9-18'" in jobs["reminder-check"]
        assert "minute='0'" in jobs["reminder-check"]
    finally:
        await manager.shutdown()

    assert manager.status == "stopped"


@pytest.mark.asyncio
async def test_startup_inside_reminder_window_runs_one_catch_up(database: Database) -> None:
    reminders = FakeReminders()
    spawned: list[Coroutine[Any, Any, Any]] = []
    now = datetime(2026, 7, 21, 10, 30, tzinfo=BEIJING)
    manager = SchedulerManager(
        database,
        FakeCalendar(),
        FakeTaxProfile(),
        reminders,
        now=lambda: now,
        spawn=spawned.append,
    )

    manager.start()
    try:
        assert len(spawned) == 1
        await spawned.pop()
    finally:
        await manager.shutdown()

    assert reminders.calls == [now]


@pytest.mark.asyncio
async def test_startup_outside_reminder_window_waits_for_schedule(database: Database) -> None:
    spawned: list[Coroutine[Any, Any, Any]] = []
    manager = SchedulerManager(
        database,
        FakeCalendar(),
        FakeTaxProfile(),
        FakeReminders(),
        now=lambda: datetime(2026, 7, 21, 8, 59, tzinfo=BEIJING),
        spawn=spawned.append,
    )

    manager.start()
    try:
        assert spawned == []
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_daily_refresh_includes_default_months_and_recent_accesses(
    database: Database,
) -> None:
    now = datetime(2026, 7, 21, 8, tzinfo=BEIJING)
    with database.session() as session, session.begin():
        session.add_all(
            [
                CalendarSyncState(
                    region_code="132000000",
                    cache_month="2026-05",
                    last_accessed_at=(now.astimezone(UTC) - timedelta(days=10)).replace(
                        tzinfo=None
                    ),
                    status="fresh",
                ),
                CalendarSyncState(
                    region_code="133000000",
                    cache_month="2026-04",
                    last_accessed_at=(now.astimezone(UTC) - timedelta(days=31)).replace(
                        tzinfo=None
                    ),
                    status="fresh",
                ),
            ]
        )
    calendar = FakeCalendar()
    manager = SchedulerManager(
        database,
        calendar,
        FakeTaxProfile("111000000"),
        FakeReminders(),
        now=lambda: now,
    )

    await manager.refresh_priority_months(now)

    assert set((region, str(month)) for region, month in calendar.calls) == {
        ("111000000", "2026-07"),
        ("111000000", "2026-08"),
        ("132000000", "2026-05"),
    }
