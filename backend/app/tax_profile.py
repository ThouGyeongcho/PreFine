import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select

from backend.app.calendar import CachedCalendarEvent
from backend.app.db import Database
from backend.app.models import TaxCatalogAlias, TaxCatalogItem, ToolSetting

TAX_TOOL_KEY = "tax_calendar"
TaxpayerType = Literal["general_taxpayer", "small_scale_taxpayer"]
DisplayMode = Literal["official", "personalized"]


class TaxToolSettings(BaseModel):
    default_mode: DisplayMode = "official"
    taxpayer_type: TaxpayerType | None = None
    selected_item_codes: list[str] = Field(default_factory=list)
    default_region_code: str | None = None
    reminder_days: list[int] = Field(default_factory=lambda: [7, 3, 1])

    @field_validator("selected_item_codes")
    @classmethod
    def unique_item_codes(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))

    @field_validator("reminder_days")
    @classmethod
    def valid_reminder_days(cls, values: list[int]) -> list[int]:
        if any(value < 0 or value > 30 for value in values):
            raise ValueError("提醒天数必须在 0 到 30 之间")
        return sorted(set(values), reverse=True)

    @property
    def profile_complete(self) -> bool:
        return self.taxpayer_type is not None and bool(self.selected_item_codes)


@dataclass(frozen=True)
class CatalogItem:
    code: str
    category: str
    display_name: str
    aliases: tuple[str, ...]
    taxpayer_scope: tuple[TaxpayerType, ...]


@dataclass(frozen=True)
class PersonalizedEvent:
    key: str
    source_event_id: str
    category: str
    item_code: str | None
    display_name: str
    official_text: str
    matched_text: str
    start_date: date
    end_date: date
    source_order: int
    needs_confirmation: bool


class Catalog:
    def __init__(self, version: int, items: list[CatalogItem]) -> None:
        self.version = version
        self.items = tuple(items)
        self.by_code = {item.code: item for item in items}
        self.by_alias: dict[str, CatalogItem] = {}
        for item in items:
            for alias in item.aliases:
                if alias in self.by_alias:
                    raise ValueError(f"duplicate catalog alias: {alias}")
                self.by_alias[alias] = item

    def match(self, upstream_text: str) -> CatalogItem | None:
        text = upstream_text.strip()
        candidates = [text]
        for prefix in ("申报缴纳", "申报"):
            if text.startswith(prefix) and len(text) > len(prefix):
                candidates.append(text[len(prefix) :])
        annual = re.fullmatch(r"申报缴纳\d{4}年度(.+)", text)
        if annual:
            candidates.append(annual.group(1))
        for candidate in candidates:
            if item := self.by_alias.get(candidate):
                return item
        return None


class InvalidTaxSettingError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@lru_cache(maxsize=1)
def load_catalog() -> Catalog:
    path = Path(__file__).parent / "data" / "tax_catalog.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = [
        CatalogItem(
            code=item["code"],
            category=item["category"],
            display_name=item["display_name"],
            aliases=tuple(item["aliases"]),
            taxpayer_scope=tuple(item["taxpayer_scope"]),
        )
        for item in raw["items"]
    ]
    return Catalog(version=raw["version"], items=items)


def filter_events(
    events: list[CachedCalendarEvent] | tuple[CachedCalendarEvent, ...],
    settings: TaxToolSettings,
    catalog: Catalog,
) -> list[PersonalizedEvent]:
    if not settings.profile_complete:
        return []
    selected_codes = set(settings.selected_item_codes)
    taxpayer_type = settings.taxpayer_type
    results: list[PersonalizedEvent] = []
    for event in events:
        for index, text in enumerate(event.split_items):
            item = catalog.match(text)
            if item is None:
                results.append(
                    PersonalizedEvent(
                        key=f"{event.source_event_id}:{index}:unknown",
                        source_event_id=event.source_event_id,
                        category="其他待确认",
                        item_code=None,
                        display_name="其他待确认",
                        official_text=event.bssz,
                        matched_text=text,
                        start_date=event.start_date,
                        end_date=event.end_date,
                        source_order=event.source_order,
                        needs_confirmation=True,
                    )
                )
                continue
            if item.code not in selected_codes or taxpayer_type not in item.taxpayer_scope:
                continue
            results.append(
                PersonalizedEvent(
                    key=f"{event.source_event_id}:{index}:{item.code}",
                    source_event_id=event.source_event_id,
                    category=item.category,
                    item_code=item.code,
                    display_name=item.display_name,
                    official_text=event.bssz,
                    matched_text=text,
                    start_date=event.start_date,
                    end_date=event.end_date,
                    source_order=event.source_order,
                    needs_confirmation=False,
                )
            )
    return results


class TaxProfileService:
    def __init__(
        self,
        database: Database,
        catalog: Catalog,
        region_codes: set[str],
    ) -> None:
        self._database = database
        self.catalog = catalog
        self._region_codes = region_codes

    def seed_catalog(self) -> None:
        with self._database.session() as session, session.begin():
            session.execute(delete(TaxCatalogAlias))
            for item in self.catalog.items:
                session.merge(
                    TaxCatalogItem(
                        code=item.code,
                        category=item.category,
                        display_name=item.display_name,
                        taxpayer_scope=list(item.taxpayer_scope),
                        enabled=True,
                    )
                )
            session.flush()
            for item in self.catalog.items:
                session.add_all(
                    [
                        TaxCatalogAlias(
                            item_code=item.code,
                            alias=alias,
                            rule_version=self.catalog.version,
                        )
                        for alias in item.aliases
                    ]
                )

    def get_settings(self) -> TaxToolSettings:
        with self._database.session() as session:
            row = session.scalar(
                select(ToolSetting).where(ToolSetting.tool_key == TAX_TOOL_KEY)
            )
            return TaxToolSettings.model_validate(row.value) if row else TaxToolSettings()

    def save_settings(self, settings: TaxToolSettings) -> TaxToolSettings:
        unknown_codes = sorted(set(settings.selected_item_codes) - self.catalog.by_code.keys())
        if unknown_codes:
            raise InvalidTaxSettingError("invalid_tax_item", "包含不支持的税务事项")
        if (
            settings.default_region_code is not None
            and settings.default_region_code not in self._region_codes
        ):
            raise InvalidTaxSettingError("invalid_region", "请选择支持的税务地区")

        stored = settings.model_dump(mode="json")
        with self._database.session() as session, session.begin():
            row = session.get(ToolSetting, TAX_TOOL_KEY)
            if row is None:
                session.add(
                    ToolSetting(
                        tool_key=TAX_TOOL_KEY,
                        value=stored,
                        updated_at=datetime.now(UTC).replace(tzinfo=None),
                    )
                )
            else:
                row.value = stored
                row.updated_at = datetime.now(UTC).replace(tzinfo=None)
        return settings
