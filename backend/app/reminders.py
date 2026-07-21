import asyncio
import hashlib
import hmac
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Protocol
from zoneinfo import ZoneInfo

import aiosmtplib

from backend.app.calendar import CalendarMonthResult
from backend.app.config import Settings
from backend.app.db import Database
from backend.app.models import EmailDispatch
from backend.app.tax_profile import PersonalizedEvent, TaxProfileService, filter_events
from backend.app.tax_source import SOURCE_PAGE_URL, YearMonth

logger = logging.getLogger(__name__)


class EmailDeliveryError(RuntimeError):
    pass


class SmtpNotConfiguredError(RuntimeError):
    pass


class CalendarReader(Protocol):
    async def get_month(
        self,
        region_code: str,
        month: YearMonth,
    ) -> CalendarMonthResult: ...


class EmailSender(Protocol):
    async def send(self, subject: str, body: str) -> None: ...


@dataclass(frozen=True)
class ReminderRunResult:
    sent: int = 0
    failed: int = 0
    skipped_duplicate: int = 0
    skipped_unconfigured: int = 0


class SmtpEmailSender:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send(self, subject: str, body: str) -> None:
        settings = self._settings
        if not settings.email_configured:
            raise SmtpNotConfiguredError("SMTP is not configured")
        message = EmailMessage()
        message["From"] = settings.smtp_from
        message["To"] = settings.reminder_to_email
        message["Subject"] = subject
        message.set_content(body)
        try:
            await aiosmtplib.send(
                message,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_username,
                password=(
                    settings.smtp_password.get_secret_value()
                    if settings.smtp_password is not None
                    else None
                ),
                use_tls=settings.smtp_use_tls,
                start_tls=settings.smtp_starttls,
                timeout=10,
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            raise EmailDeliveryError("SMTP delivery failed") from error


class ReminderService:
    def __init__(
        self,
        database: Database,
        calendar: CalendarReader,
        tax_profile: TaxProfileService,
        settings: Settings,
        sender: EmailSender,
    ) -> None:
        self._database = database
        self._calendar = calendar
        self._tax_profile = tax_profile
        self._settings = settings
        self._sender = sender
        self._check_lock = asyncio.Lock()

    async def check_due(self, now: datetime | None = None) -> ReminderRunResult:
        async with self._check_lock:
            return await self._check_due(now)

    async def _check_due(self, now: datetime | None = None) -> ReminderRunResult:
        settings = self._tax_profile.get_settings()
        if (
            not self._settings.email_configured
            or not settings.profile_complete
            or settings.default_region_code is None
        ):
            return ReminderRunResult(skipped_unconfigured=1)

        local_now = self._local_time(now)
        months = [
            YearMonth(local_now.year, local_now.month),
            _next_month(YearMonth(local_now.year, local_now.month)),
        ]
        calendar_results = [
            await self._calendar.get_month(settings.default_region_code, month)
            for month in months
        ]
        events_by_id = {
            event.source_event_id: event
            for result in calendar_results
            for event in result.events
        }
        personalized = filter_events(
            list(events_by_id.values()),
            settings,
            self._tax_profile.catalog,
        )
        groups: dict[tuple[datetime.date, int], list[PersonalizedEvent]] = {}
        for item in personalized:
            advance_days = (item.end_date - local_now.date()).days
            if advance_days in settings.reminder_days:
                groups.setdefault((item.end_date, advance_days), []).append(item)

        sent = failed = skipped_duplicate = 0
        recipient = self._settings.reminder_to_email
        assert recipient is not None
        recipient_hash = recipient_fingerprint(
            recipient,
            self._settings.session_secret.get_secret_value().encode("utf-8"),
        )
        region_name = _region_name(settings.default_region_code)
        last_updated = max(
            (
                result.last_succeeded_at
                for result in calendar_results
                if result.last_succeeded_at is not None
            ),
            default=None,
        )
        for (due_date, advance_days), items in sorted(groups.items()):
            key = reminder_key(
                settings.default_region_code,
                due_date.isoformat(),
                advance_days,
                recipient_hash,
            )
            if self._was_sent(key):
                logger.info("reminder_dispatch status=skipped_duplicate reminder_key=%s", key)
                skipped_duplicate += 1
                continue
            subject = _subject(region_name, advance_days)
            body = _body(region_name, due_date.isoformat(), items, last_updated)
            try:
                await self._sender.send(subject, body)
            except EmailDeliveryError as error:
                attempt_count = self._record_failure(
                    key,
                    settings.default_region_code,
                    due_date.isoformat(),
                    advance_days,
                    recipient_hash,
                    type(error).__name__,
                )
                logger.warning(
                    "reminder_dispatch status=failed reminder_key=%s attempt_count=%d "
                    "error_category=%s",
                    key,
                    attempt_count,
                    type(error).__name__,
                )
                failed += 1
                continue
            attempt_count = self._record_success(
                key,
                settings.default_region_code,
                due_date.isoformat(),
                advance_days,
                recipient_hash,
                local_now,
            )
            logger.info(
                "reminder_dispatch status=sent reminder_key=%s attempt_count=%d",
                key,
                attempt_count,
            )
            sent += 1
        return ReminderRunResult(
            sent=sent,
            failed=failed,
            skipped_duplicate=skipped_duplicate,
        )

    async def send_test_email(self, now: datetime | None = None) -> None:
        if not self._settings.email_configured:
            raise SmtpNotConfiguredError("SMTP is not configured")
        local_now = self._local_time(now)
        await self._sender.send(
            "[财务工具包] 测试邮件",
            f"这是一封财务工具包测试邮件。\n发送时间：{local_now.isoformat()}\n",
        )
        logger.info("test_email status=sent")

    def _local_time(self, now: datetime | None) -> datetime:
        value = now or datetime.now(UTC)
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(ZoneInfo(self._settings.timezone))

    def _was_sent(self, key: str) -> bool:
        with self._database.session() as session:
            row = session.get(EmailDispatch, key)
            return row is not None and row.status == "sent"

    def _record_failure(
        self,
        key: str,
        region_code: str,
        due_date: str,
        advance_days: int,
        recipient_hash: str,
        error_category: str,
    ) -> int:
        with self._database.session() as session, session.begin():
            row = session.get(EmailDispatch, key)
            if row is None:
                row = EmailDispatch(
                    dispatch_key=key,
                    region_code=region_code,
                    due_date=due_date,
                    advance_days=advance_days,
                    recipient_fingerprint=recipient_hash,
                    status="failed",
                    attempt_count=1,
                    last_error=error_category,
                )
                session.add(row)
            else:
                row.status = "failed"
                row.attempt_count += 1
                row.last_error = error_category
            session.flush()
            return row.attempt_count

    def _record_success(
        self,
        key: str,
        region_code: str,
        due_date: str,
        advance_days: int,
        recipient_hash: str,
        sent_at: datetime,
    ) -> int:
        storage_time = sent_at.astimezone(UTC).replace(tzinfo=None)
        with self._database.session() as session, session.begin():
            row = session.get(EmailDispatch, key)
            if row is None:
                row = EmailDispatch(
                    dispatch_key=key,
                    region_code=region_code,
                    due_date=due_date,
                    advance_days=advance_days,
                    recipient_fingerprint=recipient_hash,
                    status="sent",
                    attempt_count=1,
                    sent_at=storage_time,
                )
                session.add(row)
            else:
                row.status = "sent"
                row.attempt_count += 1
                row.last_error = None
                row.sent_at = storage_time
            session.flush()
            return row.attempt_count


def recipient_fingerprint(address: str, secret: bytes) -> str:
    normalized = address.strip().lower().encode("utf-8")
    return hmac.new(secret, normalized, hashlib.sha256).hexdigest()


def reminder_key(
    region_code: str,
    due_date: str,
    advance_days: int,
    recipient_hash: str,
) -> str:
    return f"{region_code}:{due_date}:{advance_days}:{recipient_hash}"


def _next_month(month: YearMonth) -> YearMonth:
    if month.month == 12:
        return YearMonth(month.year + 1, 1)
    return YearMonth(month.year, month.month + 1)


def _region_name(region_code: str) -> str:
    from backend.app.tax_source import load_seed_regions

    return next(
        (region.name for region in load_seed_regions() if region.code == region_code),
        region_code,
    )


def _subject(region_name: str, advance_days: int) -> str:
    if advance_days == 0:
        return f"[财务工具包] {region_name}：今天截止"
    return f"[财务工具包] {region_name}：{advance_days}天后有税务事项截止"


def _body(
    region_name: str,
    due_date: str,
    items: list[PersonalizedEvent],
    last_updated: datetime | None,
) -> str:
    lines = [f"地区：{region_name}", f"截止日期：{due_date}", "", "相关事项："]
    lines.extend(
        f"- {item.display_name}：{item.matched_text}（{item.start_date} 至 {item.end_date}）"
        for item in items
    )
    lines.extend(
        [
            "",
            f"数据更新时间：{last_updated.isoformat() if last_updated else '未知'}",
            f"12366 来源：{SOURCE_PAGE_URL}",
            "",
            "本清单为对 12366 原文的本地辅助筛选，最终以主管税务机关最新通知为准。",
        ]
    )
    return "\n".join(lines)
