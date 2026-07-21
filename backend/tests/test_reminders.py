import asyncio
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from backend.app.calendar import CachedCalendarEvent, CalendarMonthResult
from backend.app.config import Settings
from backend.app.db import Database
from backend.app.models import Base, EmailDispatch
from backend.app.reminders import EmailDeliveryError, ReminderService
from backend.app.tax_profile import TaxProfileService, TaxToolSettings, load_catalog
from backend.app.tax_source import SOURCE_PAGE_URL, YearMonth, load_seed_regions

BEIJING = timezone(timedelta(hours=8))
FROZEN_NOW = datetime(2026, 7, 21, 10, tzinfo=BEIJING)


def configured_settings(data_dir: Path) -> Settings:
    return Settings(
        ADMIN_USERNAME="admin",
        ADMIN_PASSWORD="correct horse battery staple",
        SESSION_SECRET="0123456789abcdef0123456789abcdef",
        DATA_DIR=data_dir,
        SMTP_HOST="smtp.example.test",
        SMTP_PORT=587,
        SMTP_USERNAME="mailer",
        SMTP_PASSWORD="smtp-secret",
        SMTP_FROM="finance@example.test",
        REMINDER_TO_EMAIL="owner@example.test",
        SMTP_STARTTLS=True,
    )


def make_event(
    end_date: date,
    *,
    event_id: str = "event-1",
    text: str = "申报缴纳增值税",
    items: tuple[str, ...] = ("申报缴纳增值税",),
) -> CachedCalendarEvent:
    return CachedCalendarEvent(
        source_event_id=event_id,
        start_date=end_date.replace(day=1),
        end_date=end_date,
        bssz=text,
        split_items=items,
        source_agency="国家税务总局",
        source_created_at="2025-12-29 13:40:56",
        source_order=0,
    )


class FakeCalendar:
    def __init__(self, events: list[CachedCalendarEvent]) -> None:
        self.events = events
        self.calls: list[tuple[str, YearMonth]] = []

    async def get_month(self, region_code: str, month: YearMonth) -> CalendarMonthResult:
        self.calls.append((region_code, month))
        matching = tuple(event for event in self.events if event.end_date.month == month.month)
        return CalendarMonthResult(
            region_code=region_code,
            month=month,
            events=matching,
            stale=False,
            sync_status="fresh",
            last_succeeded_at=FROZEN_NOW.astimezone(UTC),
        )


class FakeSender:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []
        self.failures_remaining = 0

    async def send(self, subject: str, body: str) -> None:
        if self.failures_remaining:
            self.failures_remaining -= 1
            raise EmailDeliveryError("sensitive smtp details")
        self.messages.append((subject, body))


class BlockingSender(FakeSender):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.call_count = 0

    async def send(self, subject: str, body: str) -> None:
        self.call_count += 1
        self.started.set()
        await self.release.wait()
        await super().send(subject, body)


@pytest.fixture
def database(tmp_path: Path) -> Database:
    value = Database(tmp_path / "reminders.db")
    Base.metadata.create_all(value.engine)
    try:
        yield value
    finally:
        value.dispose()


def make_profile(database: Database, reminder_days: list[int] | None = None) -> TaxProfileService:
    regions = load_seed_regions()
    profile = TaxProfileService(database, load_catalog(), {region.code for region in regions})
    profile.seed_catalog()
    profile.save_settings(
        TaxToolSettings(
            taxpayer_type="general_taxpayer",
            selected_item_codes=["vat"],
            default_region_code="111000000",
            reminder_days=reminder_days or [7, 3, 1, 0],
        )
    )
    return profile


@pytest.mark.asyncio
@pytest.mark.parametrize("days", [7, 3, 1, 0])
async def test_due_offsets_are_selected(
    database: Database,
    tmp_path: Path,
    days: int,
) -> None:
    event = make_event(FROZEN_NOW.date() + timedelta(days=days))
    sender = FakeSender()
    service = ReminderService(
        database,
        FakeCalendar([event]),
        make_profile(database),
        configured_settings(tmp_path),
        sender,
    )

    result = await service.check_due(FROZEN_NOW)

    assert result.sent == 1
    assert len(sender.messages) == 1
    expected_phrase = "今天截止" if days == 0 else f"{days}天后有税务事项截止"
    assert expected_phrase in sender.messages[0][0]
    assert "增值税" in sender.messages[0][1]


@pytest.mark.asyncio
async def test_same_region_date_and_offset_are_merged_into_one_email(
    database: Database,
    tmp_path: Path,
) -> None:
    due = FROZEN_NOW.date() + timedelta(days=3)
    first = make_event(due, event_id="first")
    second = make_event(
        due,
        event_id="second",
        text="神秘新税种",
        items=("神秘新税种",),
    )
    sender = FakeSender()
    service = ReminderService(
        database,
        FakeCalendar([first, second]),
        make_profile(database),
        configured_settings(tmp_path),
        sender,
    )

    result = await service.check_due(FROZEN_NOW)

    assert result.sent == 1
    assert len(sender.messages) == 1
    assert "增值税" in sender.messages[0][1]
    assert "其他待确认" in sender.messages[0][1]
    assert "神秘新税种" in sender.messages[0][1]
    assert SOURCE_PAGE_URL in sender.messages[0][1]


@pytest.mark.asyncio
async def test_success_deduplicates_but_smtp_failure_retries(
    database: Database,
    tmp_path: Path,
) -> None:
    sender = FakeSender()
    sender.failures_remaining = 1
    service = ReminderService(
        database,
        FakeCalendar([make_event(FROZEN_NOW.date() + timedelta(days=1))]),
        make_profile(database),
        configured_settings(tmp_path),
        sender,
    )

    first = await service.check_due(FROZEN_NOW)
    second = await service.check_due(FROZEN_NOW + timedelta(hours=1))
    third = await service.check_due(FROZEN_NOW + timedelta(hours=2))

    assert first.failed == 1
    assert second.sent == 1
    assert third.skipped_duplicate == 1
    assert len(sender.messages) == 1


@pytest.mark.asyncio
async def test_overlapping_checks_cannot_send_the_same_reminder_twice(
    database: Database,
    tmp_path: Path,
) -> None:
    sender = BlockingSender()
    service = ReminderService(
        database,
        FakeCalendar([make_event(FROZEN_NOW.date() + timedelta(days=1))]),
        make_profile(database),
        configured_settings(tmp_path),
        sender,
    )

    first = asyncio.create_task(service.check_due(FROZEN_NOW))
    await sender.started.wait()
    second = asyncio.create_task(service.check_due(FROZEN_NOW))
    await asyncio.sleep(0)
    sender.release.set()
    results = await asyncio.gather(first, second)

    assert sender.call_count == 1
    assert len(sender.messages) == 1
    assert sorted((result.sent, result.skipped_duplicate) for result in results) == [
        (0, 1),
        (1, 0),
    ]


@pytest.mark.asyncio
async def test_next_month_is_checked_for_cross_month_deadlines(
    database: Database,
    tmp_path: Path,
) -> None:
    now = datetime(2026, 7, 31, 10, tzinfo=BEIJING)
    event = make_event(date(2026, 8, 1))
    calendar = FakeCalendar([event])
    sender = FakeSender()
    service = ReminderService(
        database,
        calendar,
        make_profile(database),
        configured_settings(tmp_path),
        sender,
    )

    result = await service.check_due(now)

    assert result.sent == 1
    assert [str(month) for _, month in calendar.calls] == ["2026-07", "2026-08"]


@pytest.mark.asyncio
async def test_dispatch_storage_contains_a_fingerprint_not_the_recipient(
    database: Database,
    tmp_path: Path,
) -> None:
    service = ReminderService(
        database,
        FakeCalendar([make_event(FROZEN_NOW.date() + timedelta(days=1))]),
        make_profile(database),
        configured_settings(tmp_path),
        FakeSender(),
    )

    await service.check_due(FROZEN_NOW)

    with database.session() as session:
        dispatch = session.scalar(select(EmailDispatch))
    assert dispatch is not None
    assert len(dispatch.recipient_fingerprint) == 64
    assert "owner@example.test" not in dispatch.recipient_fingerprint


@pytest.mark.asyncio
async def test_test_email_does_not_create_business_deduplication(
    database: Database,
    tmp_path: Path,
) -> None:
    sender = FakeSender()
    service = ReminderService(
        database,
        FakeCalendar([]),
        make_profile(database),
        configured_settings(tmp_path),
        sender,
    )

    await service.send_test_email(FROZEN_NOW)

    with database.session() as session:
        dispatches = session.scalars(select(EmailDispatch)).all()
    assert dispatches == []
    assert sender.messages[0][0] == "[财务工具包] 测试邮件"


def test_tls_and_starttls_cannot_both_be_enabled(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        Settings(
            ADMIN_USERNAME="admin",
            ADMIN_PASSWORD="secret",
            SESSION_SECRET="0123456789abcdef0123456789abcdef",
            DATA_DIR=tmp_path,
            SMTP_HOST="smtp.example.test",
            SMTP_PORT=465,
            SMTP_FROM="finance@example.test",
            REMINDER_TO_EMAIL="owner@example.test",
            SMTP_USE_TLS=True,
            SMTP_STARTTLS=True,
        )
