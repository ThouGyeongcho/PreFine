import asyncio
import hashlib
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

SOURCE_BASE_URL = "https://12366.chinatax.gov.cn"
SOURCE_PAGE_URL = f"{SOURCE_BASE_URL}/wap/pages/taxcalendar/tax-calendar.html"
REGIONS_PATH = "/core-plugins/12366/js/provinces.json"
CALENDAR_PATH = "/bsfw/calendar/getCalendarListForMonth"
UPSTREAM_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class TaxSourceError(RuntimeError):
    pass


class TaxSourceUnavailableError(TaxSourceError):
    pass


class TaxSourceBusinessError(TaxSourceError):
    pass


class TaxSourceProtocolError(TaxSourceError):
    pass


@dataclass(frozen=True, order=True)
class YearMonth:
    year: int
    month: int

    def __post_init__(self) -> None:
        if self.year < 2000 or self.year > 9999 or self.month < 1 or self.month > 12:
            raise ValueError("invalid year-month")

    def __str__(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"

    @classmethod
    def parse(cls, value: str) -> "YearMonth":
        if re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])", value) is None:
            raise ValueError("invalid year-month")
        return cls(int(value[:4]), int(value[5:]))


@dataclass(frozen=True)
class Region:
    code: str
    name: str
    region_code: str


@dataclass(frozen=True)
class SourceCalendarEvent:
    source_event_id: str
    start_date: date
    end_date: date
    bssz: str
    split_items: tuple[str, ...]
    source_agency: str | None
    source_created_at: str | None
    source_region_name: str | None
    remark: str | None
    source_order: int


class _UpstreamCalendarItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source_event_id: str | None = Field(default=None, alias="rlid")
    start_at: str = Field(alias="bskssj")
    end_at: str = Field(alias="bsjssj")
    bssz: str
    source_agency: str | None = Field(default=None, alias="cjrjgmc")
    source_created_at: str | None = Field(default=None, alias="cjsj")
    source_region_name: str | None = Field(default=None, alias="ssjgmc")
    remark: str | None = Field(default=None, alias="bz")


class _UpstreamCalendarPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    events: list[_UpstreamCalendarItem] = Field(alias="list")


class _UpstreamCalendarResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status_code: str = Field(alias="statusCode")
    payload: _UpstreamCalendarPayload = Field(alias="json")


class _UpstreamRegion(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code: str = Field(alias="unitcode")
    name: str = Field(alias="unitdz")
    region_code: str = Field(alias="unitregion")


class _UpstreamRegionsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    regions: list[_UpstreamRegion] = Field(alias="value")
    count: int = Field(alias="Count")


def load_seed_regions() -> list[Region]:
    path = Path(__file__).parent / "data" / "regions.json"
    raw_regions = json.loads(path.read_text(encoding="utf-8"))
    return [Region(**item) for item in raw_regions]


class TaxSourceClient:
    """Validated adapter around the undocumented 12366 calendar endpoints."""

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._sleep = sleep
        self._client = httpx.AsyncClient(
            base_url=SOURCE_BASE_URL,
            transport=transport,
            follow_redirects=True,
            headers={
                "Accept": "application/json, text/plain, */*",
                "Referer": SOURCE_PAGE_URL,
                "User-Agent": "PreFine/0.1 (+https://github.com/ThouGyeongcho/PreFine)",
            },
            timeout=10.0,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch_regions(self) -> list[Region]:
        response = await self._request("GET", REGIONS_PATH)
        payload = self._json(response)
        try:
            validated = _UpstreamRegionsResponse.model_validate(payload)
        except ValidationError as error:
            raise TaxSourceProtocolError("12366 region response shape changed") from error
        if validated.count != len(validated.regions):
            raise TaxSourceProtocolError("12366 region count did not match its list")
        regions = [Region(**item.model_dump()) for item in validated.regions]
        if len({region.code for region in regions}) != len(regions):
            raise TaxSourceProtocolError("12366 returned duplicate region codes")
        return regions

    async def fetch_month(
        self,
        region_code: str,
        month: YearMonth,
    ) -> list[SourceCalendarEvent]:
        response = await self._request(
            "POST",
            CALENDAR_PATH,
            data={"ssjg": region_code, "bssj": str(month)},
        )
        raw_payload = self._json(response)
        if not isinstance(raw_payload, dict) or not isinstance(
            raw_payload.get("statusCode"), str
        ):
            raise TaxSourceProtocolError("12366 calendar status was missing")
        if raw_payload["statusCode"] != "200":
            raise TaxSourceBusinessError("12366 rejected the calendar request")
        try:
            payload = _UpstreamCalendarResponse.model_validate(raw_payload)
        except ValidationError as error:
            raise TaxSourceProtocolError("12366 calendar response shape changed") from error

        events: list[SourceCalendarEvent] = []
        for index, item in enumerate(payload.payload.events):
            try:
                start_date = datetime.strptime(item.start_at, UPSTREAM_DATE_FORMAT).date()
                end_date = datetime.strptime(item.end_at, UPSTREAM_DATE_FORMAT).date()
            except ValueError as error:
                raise TaxSourceProtocolError("12366 returned an invalid calendar date") from error
            if start_date > end_date:
                raise TaxSourceProtocolError("12366 returned a reversed calendar date range")
            source_event_id = item.source_event_id or _stable_event_id(
                region_code,
                start_date,
                end_date,
                item.bssz,
            )
            events.append(
                SourceCalendarEvent(
                    source_event_id=source_event_id,
                    start_date=start_date,
                    end_date=end_date,
                    bssz=item.bssz,
                    split_items=_split_items(item.bssz),
                    source_agency=item.source_agency,
                    source_created_at=item.source_created_at,
                    source_region_name=item.source_region_name,
                    remark=item.remark,
                    source_order=index,
                )
            )
        return events

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response:
        for attempt in range(2):
            try:
                response = await self._client.request(method, path, **kwargs)
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as error:
                retryable = error.response.status_code >= 500
                if attempt == 0 and retryable:
                    await self._sleep(0.25)
                    continue
                raise TaxSourceUnavailableError("12366 HTTP request failed") from error
            except (httpx.TimeoutException, httpx.TransportError) as error:
                if attempt == 0:
                    await self._sleep(0.25)
                    continue
                raise TaxSourceUnavailableError("12366 network request failed") from error
        raise AssertionError("unreachable")

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as error:
            raise TaxSourceProtocolError("12366 returned invalid JSON") from error


def _stable_event_id(region_code: str, start_date: date, end_date: date, bssz: str) -> str:
    content = "\x1f".join((region_code, start_date.isoformat(), end_date.isoformat(), bssz))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _split_items(bssz: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in re.split(r"[、，,；;]", bssz) if item.strip())
