import asyncio
from collections.abc import Coroutine
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from backend.app.calendar import CalendarService, CalendarUnavailableError
from backend.app.db import Database
from backend.app.models import Base
from backend.app.tax_source import SourceCalendarEvent, TaxSourceUnavailableError, YearMonth


def make_event(event_id: str = "event-1", text: str = "官方原文") -> SourceCalendarEvent:
    return SourceCalendarEvent(
        source_event_id=event_id,
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 15),
        bssz=text,
        split_items=(text,),
        source_agency="国家税务总局",
        source_created_at="2025-12-29 13:40:56",
        source_region_name="北京市税务局",
        remark="",
        source_order=0,
    )


class FakeTaxSource:
    def __init__(self, events: list[SourceCalendarEvent] | None = None) -> None:
        self.events = events or []
        self.error: Exception | None = None
        self.call_count = 0
        self.gate: asyncio.Event | None = None

    async def fetch_month(
        self,
        region_code: str,
        month: YearMonth,
    ) -> list[SourceCalendarEvent]:
        self.call_count += 1
        if self.gate is not None:
            await self.gate.wait()
        if self.error is not None:
            raise self.error
        return list(self.events)


@pytest.fixture
def database(tmp_path: Path) -> Database:
    value = Database(tmp_path / "calendar.db")
    Base.metadata.create_all(value.engine)
    try:
        yield value
    finally:
        value.dispose()


@pytest.mark.asyncio
async def test_first_read_waits_for_sync(database: Database) -> None:
    source = FakeTaxSource([make_event()])
    now = datetime(2026, 7, 21, 1, tzinfo=UTC)
    service = CalendarService(database, source, now=lambda: now)

    result = await service.get_month("111000000", YearMonth(2026, 7))

    assert source.call_count == 1
    assert result.stale is False
    assert result.sync_status == "fresh"
    assert result.events[0].bssz == "官方原文"


@pytest.mark.asyncio
async def test_fresh_cache_avoids_upstream(database: Database) -> None:
    source = FakeTaxSource([make_event()])
    current = [datetime(2026, 7, 21, 1, tzinfo=UTC)]
    service = CalendarService(database, source, now=lambda: current[0])
    await service.get_month("111000000", YearMonth(2026, 7))
    source.call_count = 0
    current[0] += timedelta(hours=23, minutes=59)

    result = await service.get_month("111000000", YearMonth(2026, 7))

    assert source.call_count == 0
    assert result.sync_status == "fresh"
    assert result.stale is False


@pytest.mark.asyncio
async def test_stale_cache_returns_before_background_refresh(database: Database) -> None:
    source = FakeTaxSource([make_event(text="旧原文")])
    current = [datetime(2026, 7, 21, 1, tzinfo=UTC)]
    spawned: list[Coroutine[Any, Any, Any]] = []
    service = CalendarService(
        database,
        source,
        now=lambda: current[0],
        spawn=spawned.append,
    )
    await service.get_month("111000000", YearMonth(2026, 7))
    source.events = [make_event(text="新原文")]
    source.call_count = 0
    current[0] += timedelta(hours=24, seconds=1)

    stale = await service.get_month("111000000", YearMonth(2026, 7))

    assert stale.stale is True
    assert stale.sync_status == "stale_refreshing"
    assert stale.events[0].bssz == "旧原文"
    assert source.call_count == 0
    assert len(spawned) == 1

    await spawned.pop()
    refreshed = await service.get_month("111000000", YearMonth(2026, 7))
    assert refreshed.events[0].bssz == "新原文"


@pytest.mark.asyncio
async def test_failed_refresh_preserves_official_rows(database: Database) -> None:
    source = FakeTaxSource([make_event(text="不可改写的旧原文")])
    current = [datetime(2026, 7, 21, 1, tzinfo=UTC)]
    service = CalendarService(database, source, now=lambda: current[0])
    await service.sync_month("111000000", YearMonth(2026, 7))
    current[0] += timedelta(days=2)
    source.error = TaxSourceUnavailableError("network down")

    result = await service.sync_month("111000000", YearMonth(2026, 7))

    assert result.stale is True
    assert result.sync_status == "failed_using_cache"
    assert result.events[0].bssz == "不可改写的旧原文"


@pytest.mark.asyncio
async def test_failed_background_refresh_is_observable_without_retry_loop(
    database: Database,
) -> None:
    source = FakeTaxSource([make_event(text="不可改写的旧原文")])
    current = [datetime(2026, 7, 21, 1, tzinfo=UTC)]
    spawned: list[Coroutine[Any, Any, Any]] = []
    service = CalendarService(
        database,
        source,
        now=lambda: current[0],
        spawn=spawned.append,
    )
    await service.sync_month("111000000", YearMonth(2026, 7))
    current[0] += timedelta(days=2)
    source.error = TaxSourceUnavailableError("network down")

    refreshing = await service.get_month("111000000", YearMonth(2026, 7))
    assert refreshing.sync_status == "stale_refreshing"
    assert len(spawned) == 1
    failed = await spawned.pop()
    assert failed.sync_status == "failed_using_cache"

    observed = await service.get_month("111000000", YearMonth(2026, 7))

    assert observed.sync_status == "failed_using_cache"
    assert observed.events[0].bssz == "不可改写的旧原文"
    assert spawned == []


@pytest.mark.asyncio
async def test_first_sync_failure_without_cache_is_unavailable(database: Database) -> None:
    source = FakeTaxSource()
    source.error = TaxSourceUnavailableError("network down")
    service = CalendarService(
        database,
        source,
        now=lambda: datetime(2026, 7, 21, 1, tzinfo=UTC),
    )

    with pytest.raises(CalendarUnavailableError):
        await service.get_month("111000000", YearMonth(2026, 7))


@pytest.mark.asyncio
async def test_successful_sync_transactionally_replaces_the_month(database: Database) -> None:
    source = FakeTaxSource([make_event("old", "旧原文")])
    current = [datetime(2026, 7, 21, 1, tzinfo=UTC)]
    service = CalendarService(database, source, now=lambda: current[0])
    await service.sync_month("111000000", YearMonth(2026, 7))
    source.events = [make_event("new", "新原文")]
    current[0] += timedelta(minutes=1)

    result = await service.sync_month("111000000", YearMonth(2026, 7))

    assert [event.source_event_id for event in result.events] == ["new"]
    assert [event.bssz for event in result.events] == ["新原文"]


@pytest.mark.asyncio
async def test_concurrent_first_sync_is_deduplicated(database: Database) -> None:
    source = FakeTaxSource([make_event()])
    source.gate = asyncio.Event()
    service = CalendarService(
        database,
        source,
        now=lambda: datetime(2026, 7, 21, 1, tzinfo=UTC),
    )

    first = asyncio.create_task(service.get_month("111000000", YearMonth(2026, 7)))
    second = asyncio.create_task(service.get_month("111000000", YearMonth(2026, 7)))
    await asyncio.sleep(0)
    source.gate.set()
    results = await asyncio.gather(first, second)

    assert source.call_count == 1
    assert [result.events[0].source_event_id for result in results] == ["event-1", "event-1"]
