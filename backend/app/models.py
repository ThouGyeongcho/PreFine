from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class CalendarEvent(Base):
    __tablename__ = "calendar_events"
    __table_args__ = (
        UniqueConstraint(
            "region_code",
            "cache_month",
            "source_event_id",
            name="uq_calendar_event_source",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    region_code: Mapped[str] = mapped_column(String(32), index=True)
    cache_month: Mapped[str] = mapped_column(String(7), index=True)
    source_event_id: Mapped[str] = mapped_column(String(128))
    start_date: Mapped[str] = mapped_column(String(10))
    end_date: Mapped[str] = mapped_column(String(10))
    official_text: Mapped[str] = mapped_column(Text)
    split_items: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_agency: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_created_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_order: Mapped[int] = mapped_column(Integer)


class CalendarSyncState(Base):
    __tablename__ = "calendar_sync_state"
    __table_args__ = (
        UniqueConstraint("region_code", "cache_month", name="uq_calendar_sync_month"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    region_code: Mapped[str] = mapped_column(String(32), index=True)
    cache_month: Mapped[str] = mapped_column(String(7), index=True)
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_attempted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_succeeded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default="never")
    error_summary: Mapped[str | None] = mapped_column(String(255), nullable=True)


class TaxCatalogItem(Base):
    __tablename__ = "tax_catalog_items"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    category: Mapped[str] = mapped_column(String(32))
    display_name: Mapped[str] = mapped_column(String(128))
    taxpayer_scope: Mapped[list[str]] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class TaxCatalogAlias(Base):
    __tablename__ = "tax_catalog_aliases"
    __table_args__ = (
        UniqueConstraint("item_code", "alias", "rule_version", name="uq_tax_catalog_alias"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_code: Mapped[str] = mapped_column(ForeignKey("tax_catalog_items.code"))
    alias: Mapped[str] = mapped_column(String(255))
    rule_version: Mapped[int] = mapped_column(Integer, default=1)


class ToolSetting(Base):
    __tablename__ = "tool_settings"

    tool_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EmailDispatch(Base):
    __tablename__ = "email_dispatches"

    dispatch_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    region_code: Mapped[str] = mapped_column(String(32), index=True)
    due_date: Mapped[str] = mapped_column(String(10))
    advance_days: Mapped[int] = mapped_column(Integer)
    recipient_fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
