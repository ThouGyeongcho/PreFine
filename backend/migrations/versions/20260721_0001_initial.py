"""Create the finance toolkit v1 schema.

Revision ID: 20260721_0001
Revises:
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260721_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "calendar_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("region_code", sa.String(length=32), nullable=False),
        sa.Column("cache_month", sa.String(length=7), nullable=False),
        sa.Column("source_event_id", sa.String(length=128), nullable=False),
        sa.Column("start_date", sa.String(length=10), nullable=False),
        sa.Column("end_date", sa.String(length=10), nullable=False),
        sa.Column("official_text", sa.Text(), nullable=False),
        sa.Column("split_items", sa.JSON(), nullable=False),
        sa.Column("source_agency", sa.String(length=255), nullable=True),
        sa.Column("source_created_at", sa.String(length=64), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_order", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "region_code",
            "cache_month",
            "source_event_id",
            name="uq_calendar_event_source",
        ),
    )
    op.create_index("ix_calendar_events_region_code", "calendar_events", ["region_code"])
    op.create_index("ix_calendar_events_cache_month", "calendar_events", ["cache_month"])

    op.create_table(
        "calendar_sync_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("region_code", sa.String(length=32), nullable=False),
        sa.Column("cache_month", sa.String(length=7), nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_succeeded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_summary", sa.String(length=255), nullable=True),
        sa.UniqueConstraint("region_code", "cache_month", name="uq_calendar_sync_month"),
    )
    op.create_index(
        "ix_calendar_sync_state_region_code", "calendar_sync_state", ["region_code"]
    )
    op.create_index(
        "ix_calendar_sync_state_cache_month", "calendar_sync_state", ["cache_month"]
    )

    op.create_table(
        "tax_catalog_items",
        sa.Column("code", sa.String(length=64), primary_key=True),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("taxpayer_scope", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "tax_catalog_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "item_code",
            sa.String(length=64),
            sa.ForeignKey("tax_catalog_items.code"),
            nullable=False,
        ),
        sa.Column("alias", sa.String(length=255), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("item_code", "alias", "rule_version", name="uq_tax_catalog_alias"),
    )
    op.create_table(
        "tool_settings",
        sa.Column("tool_key", sa.String(length=64), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "email_dispatches",
        sa.Column("dispatch_key", sa.String(length=255), primary_key=True),
        sa.Column("region_code", sa.String(length=32), nullable=False),
        sa.Column("due_date", sa.String(length=10), nullable=False),
        sa.Column("advance_days", sa.Integer(), nullable=False),
        sa.Column("recipient_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(length=255), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_email_dispatches_region_code", "email_dispatches", ["region_code"])


def downgrade() -> None:
    op.drop_index("ix_email_dispatches_region_code", table_name="email_dispatches")
    op.drop_table("email_dispatches")
    op.drop_table("tool_settings")
    op.drop_table("tax_catalog_aliases")
    op.drop_table("tax_catalog_items")
    op.drop_index("ix_calendar_sync_state_cache_month", table_name="calendar_sync_state")
    op.drop_index("ix_calendar_sync_state_region_code", table_name="calendar_sync_state")
    op.drop_table("calendar_sync_state")
    op.drop_index("ix_calendar_events_cache_month", table_name="calendar_events")
    op.drop_index("ix_calendar_events_region_code", table_name="calendar_events")
    op.drop_table("calendar_events")
