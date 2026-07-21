import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from backend.app.tax_source import (
    TaxSourceBusinessError,
    TaxSourceClient,
    TaxSourceProtocolError,
    YearMonth,
    load_seed_regions,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def json_response(payload: dict[str, Any], status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=payload)


@pytest.mark.asyncio
async def test_maps_valid_month_without_rewriting_bssz() -> None:
    fixture = load_fixture("tax_calendar_success.json")
    observed_form: dict[str, list[str]] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed_form.update(parse_qs(request.content.decode("utf-8")))
        return json_response(fixture)

    client = TaxSourceClient(transport=httpx.MockTransport(handler))
    try:
        events = await client.fetch_month("111000000", YearMonth(2026, 7))
    finally:
        await client.aclose()

    assert observed_form == {"ssjg": ["111000000"], "bssj": ["2026-07"]}
    assert events[0].bssz == fixture["json"]["list"][0]["bssz"]
    assert events[0].start_date.isoformat() == "2026-07-01"
    assert events[0].end_date.isoformat() == "2026-07-15"
    assert events[0].source_event_id == "d2ab0a3b8e5a449984eb165f3da34b79"


@pytest.mark.asyncio
async def test_empty_month_is_a_valid_response() -> None:
    transport = httpx.MockTransport(
        lambda _: json_response(load_fixture("tax_calendar_empty.json"))
    )
    client = TaxSourceClient(transport=transport)
    try:
        assert await client.fetch_month("111000000", YearMonth(2026, 8)) == []
    finally:
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutate",
    [
        lambda body: body.pop("json"),
        lambda body: body["json"].update({"list": {}}),
        lambda body: body["json"]["list"][0].pop("bskssj"),
        lambda body: body["json"]["list"][0].update({"bsjssj": "July 15"}),
        lambda body: body["json"]["list"][0].update({"bssz": None}),
    ],
)
async def test_rejects_malformed_upstream(
    mutate: Callable[[dict[str, Any]], object],
) -> None:
    fixture = load_fixture("tax_calendar_success.json")
    mutate(fixture)
    client = TaxSourceClient(transport=httpx.MockTransport(lambda _: json_response(fixture)))
    try:
        with pytest.raises(TaxSourceProtocolError):
            await client.fetch_month("111000000", YearMonth(2026, 7))
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_business_failure_is_classified_without_exposing_the_response() -> None:
    fixture = load_fixture("tax_calendar_empty.json")
    fixture["statusCode"] = "500"
    fixture["message"] = "sensitive upstream diagnostic"
    client = TaxSourceClient(transport=httpx.MockTransport(lambda _: json_response(fixture)))
    try:
        with pytest.raises(TaxSourceBusinessError) as caught:
            await client.fetch_month("111000000", YearMonth(2026, 7))
    finally:
        await client.aclose()

    assert "sensitive upstream diagnostic" not in str(caught.value)


@pytest.mark.asyncio
async def test_timeout_is_retried_once() -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ReadTimeout("upstream timed out")
        return json_response(load_fixture("tax_calendar_empty.json"))

    async def no_sleep(_: float) -> None:
        return None

    client = TaxSourceClient(
        transport=httpx.MockTransport(handler),
        sleep=no_sleep,
    )
    try:
        assert await client.fetch_month("111000000", YearMonth(2026, 7)) == []
    finally:
        await client.aclose()

    assert attempts == 2


@pytest.mark.asyncio
async def test_missing_source_id_uses_a_stable_content_hash() -> None:
    fixture = load_fixture("tax_calendar_success.json")
    fixture["json"]["list"][0].pop("rlid")
    client = TaxSourceClient(transport=httpx.MockTransport(lambda _: json_response(fixture)))
    try:
        first = await client.fetch_month("111000000", YearMonth(2026, 7))
        second = await client.fetch_month("111000000", YearMonth(2026, 7))
    finally:
        await client.aclose()

    assert first[0].source_event_id == second[0].source_event_id
    assert len(first[0].source_event_id) == 64


def test_offline_seed_contains_the_current_36_unique_regions() -> None:
    regions = load_seed_regions()

    assert len(regions) == 36
    assert len({region.code for region in regions}) == 36
    assert [region.name for region in regions[:4]] == ["北京", "天津", "河北", "山西"]
    assert [region.name for region in regions[-5:]] == ["大连", "宁波", "厦门", "青岛", "深圳"]
