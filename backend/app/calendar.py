import asyncio
import logging
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.db import Database
from backend.app.models import CalendarEvent, CalendarSyncState
from backend.app.tax_source import (
    SOURCE_PAGE_URL,
    SourceCalendarEvent,
    TaxSourceError,
    YearMonth,
)

CACHE_FRESHNESS = timedelta(hours=24)
FAILED_RETRY_DELAY = timedelta(minutes=15)
logger = logging.getLogger(__name__)


class CalendarUnavailableError(RuntimeError):
    pass


class CalendarSource(Protocol):
    async def fetch_month(
        self,
        region_code: str,
        month: YearMonth,
    ) -> list[SourceCalendarEvent]: ...


@dataclass(frozen=True)
class CachedCalendarEvent:
    source_event_id: str
    start_date: date
    end_date: date
    bssz: str
    split_items: tuple[str, ...]
    source_agency: str | None
    source_created_at: str | None
    source_order: int


@dataclass(frozen=True)
class CalendarMonthResult:
    region_code: str
    month: YearMonth
    events: tuple[CachedCalendarEvent, ...]
    stale: bool
    sync_status: str
    last_succeeded_at: datetime | None
    source_url: str = SOURCE_PAGE_URL


class CalendarService:
    """Coordinates lazy month caching and validated transactional refreshes."""

    def __init__(
        self,
        database: Database,
        source: CalendarSource,
        *,
        now: Callable[[], datetime] | None = None,
        spawn: Callable[[Coroutine[Any, Any, Any]], Any] | None = None,
    ) -> None:
        self._database = database
        self._source = source
        self._now = now or (lambda: datetime.now(UTC))
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._spawn = spawn or self._spawn_background

    async def get_month(
        self,
        region_code: str,
        month: YearMonth,
    ) -> CalendarMonthResult:
        now = self._utc_now()
        self._touch_access(region_code, month, now)
        events, last_succeeded_at = self._read_cache(region_code, month)
        if last_succeeded_at is None:
            return await self.sync_month(region_code, month)

        stale = now - last_succeeded_at >= CACHE_FRESHNESS
        if not stale:
            return self._result(
                region_code,
                month,
                events,
                last_succeeded_at,
                stale=False,
                status="fresh",
            )

        persisted_status, last_attempted_at = self._read_sync_status(region_code, month)
        attempt_is_recent = (
            last_attempted_at is not None and now - last_attempted_at < FAILED_RETRY_DELAY
        )
        if persisted_status == "failed" and attempt_is_recent:
            return self._result(
                region_code,
                month,
                events,
                last_succeeded_at,
                stale=True,
                status="failed_using_cache",
            )
        if persisted_status == "syncing" and attempt_is_recent:
            return self._result(
                region_code,
                month,
                events,
                last_succeeded_at,
                stale=True,
                status="stale_refreshing",
            )

        self._spawn(self.sync_month(region_code, month))
        return self._result(
            region_code,
            month,
            events,
            last_succeeded_at,
            stale=True,
            status="stale_refreshing",
        )

    async def sync_month(
        self,
        region_code: str,
        month: YearMonth,
    ) -> CalendarMonthResult:
        started = time.monotonic()
        observed_success = self._read_cache(region_code, month)[1]
        key = (region_code, str(month))
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            current_events, current_success = self._read_cache(region_code, month)
            if current_success is not None and current_success != observed_success:
                return self._result(
                    region_code,
                    month,
                    current_events,
                    current_success,
                    stale=False,
                    status="fresh",
                )

            attempted_at = self._utc_now()
            self._mark_attempt(region_code, month, attempted_at)
            try:
                source_events = await self._source.fetch_month(region_code, month)
            except TaxSourceError as error:
                self._mark_failure(region_code, month, attempted_at, type(error).__name__)
                logger.warning(
                    "calendar_sync status=failed region_code=%s month=%s duration_ms=%d "
                    "error_category=%s",
                    region_code,
                    month,
                    round((time.monotonic() - started) * 1000),
                    type(error).__name__,
                )
                cached_events, cached_success = self._read_cache(region_code, month)
                if cached_success is None:
                    raise CalendarUnavailableError("calendar source unavailable") from error
                return self._result(
                    region_code,
                    month,
                    cached_events,
                    cached_success,
                    stale=True,
                    status="failed_using_cache",
                )

            succeeded_at = self._utc_now()
            self._replace_month(region_code, month, source_events, succeeded_at)
            logger.info(
                "calendar_sync status=succeeded region_code=%s month=%s duration_ms=%d "
                "event_count=%d",
                region_code,
                month,
                round((time.monotonic() - started) * 1000),
                len(source_events),
            )
            events, last_succeeded_at = self._read_cache(region_code, month)
            return self._result(
                region_code,
                month,
                events,
                last_succeeded_at,
                stale=False,
                status="fresh",
            )

    def _spawn_background(self, coroutine: Coroutine[Any, Any, Any]) -> None:
        task = asyncio.create_task(coroutine)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def _utc_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _touch_access(self, region_code: str, month: YearMonth, at: datetime) -> None:
        with self._database.session() as session, session.begin():
            state = self._state(session, region_code, month)
            state.last_accessed_at = _to_storage_time(at)

    def _mark_attempt(self, region_code: str, month: YearMonth, at: datetime) -> None:
        with self._database.session() as session, session.begin():
            state = self._state(session, region_code, month)
            state.last_attempted_at = _to_storage_time(at)
            state.status = "syncing"
            state.error_summary = None

    def _mark_failure(
        self,
        region_code: str,
        month: YearMonth,
        at: datetime,
        error_summary: str,
    ) -> None:
        with self._database.session() as session, session.begin():
            state = self._state(session, region_code, month)
            state.last_attempted_at = _to_storage_time(at)
            state.status = "failed"
            state.error_summary = error_summary[:255]

    def _replace_month(
        self,
        region_code: str,
        month: YearMonth,
        events: list[SourceCalendarEvent],
        fetched_at: datetime,
    ) -> None:
        cache_month = str(month)
        storage_time = _to_storage_time(fetched_at)
        with self._database.session() as session, session.begin():
            session.execute(
                delete(CalendarEvent).where(
                    CalendarEvent.region_code == region_code,
                    CalendarEvent.cache_month == cache_month,
                )
            )
            session.add_all(
                [
                    CalendarEvent(
                        region_code=region_code,
                        cache_month=cache_month,
                        source_event_id=event.source_event_id,
                        start_date=event.start_date.isoformat(),
                        end_date=event.end_date.isoformat(),
                        official_text=event.bssz,
                        split_items=list(event.split_items),
                        source_agency=event.source_agency,
                        source_created_at=event.source_created_at,
                        fetched_at=storage_time,
                        source_order=event.source_order,
                    )
                    for event in events
                ]
            )
            state = self._state(session, region_code, month)
            state.last_attempted_at = storage_time
            state.last_succeeded_at = storage_time
            state.status = "fresh"
            state.error_summary = None

    def _read_cache(
        self,
        region_code: str,
        month: YearMonth,
    ) -> tuple[tuple[CachedCalendarEvent, ...], datetime | None]:
        cache_month = str(month)
        with self._database.session() as session:
            models = session.scalars(
                select(CalendarEvent)
                .where(
                    CalendarEvent.region_code == region_code,
                    CalendarEvent.cache_month == cache_month,
                )
                .order_by(CalendarEvent.source_order, CalendarEvent.id)
            ).all()
            state = session.scalar(
                select(CalendarSyncState).where(
                    CalendarSyncState.region_code == region_code,
                    CalendarSyncState.cache_month == cache_month,
                )
            )
            events = tuple(
                CachedCalendarEvent(
                    source_event_id=model.source_event_id,
                    start_date=date.fromisoformat(model.start_date),
                    end_date=date.fromisoformat(model.end_date),
                    bssz=model.official_text,
                    split_items=tuple(model.split_items),
                    source_agency=model.source_agency,
                    source_created_at=model.source_created_at,
                    source_order=model.source_order,
                )
                for model in models
            )
            last_succeeded_at = (
                _from_storage_time(state.last_succeeded_at)
                if state is not None and state.last_succeeded_at is not None
                else None
            )
        return events, last_succeeded_at

    def _read_sync_status(
        self,
        region_code: str,
        month: YearMonth,
    ) -> tuple[str | None, datetime | None]:
        with self._database.session() as session:
            state = session.scalar(
                select(CalendarSyncState).where(
                    CalendarSyncState.region_code == region_code,
                    CalendarSyncState.cache_month == str(month),
                )
            )
            if state is None:
                return None, None
            last_attempted_at = (
                _from_storage_time(state.last_attempted_at)
                if state.last_attempted_at is not None
                else None
            )
            return state.status, last_attempted_at

    @staticmethod
    def _state(
        session: Session,
        region_code: str,
        month: YearMonth,
    ) -> CalendarSyncState:
        cache_month = str(month)
        state = session.scalar(
            select(CalendarSyncState).where(
                CalendarSyncState.region_code == region_code,
                CalendarSyncState.cache_month == cache_month,
            )
        )
        if state is None:
            state = CalendarSyncState(region_code=region_code, cache_month=cache_month)
            session.add(state)
        return state

    @staticmethod
    def _result(
        region_code: str,
        month: YearMonth,
        events: tuple[CachedCalendarEvent, ...],
        last_succeeded_at: datetime | None,
        *,
        stale: bool,
        status: str,
    ) -> CalendarMonthResult:
        return CalendarMonthResult(
            region_code=region_code,
            month=month,
            events=events,
            stale=stale,
            sync_status=status,
            last_succeeded_at=last_succeeded_at,
        )


def _to_storage_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _from_storage_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
