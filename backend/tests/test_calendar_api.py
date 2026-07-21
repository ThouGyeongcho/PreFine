from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.tax_source import SourceCalendarEvent, TaxSourceUnavailableError, YearMonth


class FakeTaxSource:
    def __init__(self) -> None:
        self.events = [
            SourceCalendarEvent(
                source_event_id="official-1",
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 15),
                bssz="申报缴纳增值税、消费税",
                split_items=("申报缴纳增值税", "消费税"),
                source_agency="国家税务总局",
                source_created_at="2025-12-29 13:40:56",
                source_region_name="北京市税务局",
                remark="",
                source_order=0,
            )
        ]
        self.error: Exception | None = None
        self.call_count = 0

    async def fetch_month(
        self,
        region_code: str,
        month: YearMonth,
    ) -> list[SourceCalendarEvent]:
        self.call_count += 1
        if self.error:
            raise self.error
        return list(self.events)


def make_client(data_dir: Path, source: FakeTaxSource) -> TestClient:
    settings = Settings(
        ADMIN_USERNAME="admin",
        ADMIN_PASSWORD="correct horse battery staple",
        SESSION_SECRET="0123456789abcdef0123456789abcdef",
        DATA_DIR=data_dir,
    )
    return TestClient(create_app(settings, start_scheduler=False, tax_source=source))


def login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "correct horse battery staple"},
    )
    assert response.status_code == 204


def test_regions_api_requires_authentication_and_returns_36_regions(tmp_path: Path) -> None:
    source = FakeTaxSource()
    with make_client(tmp_path, source) as client:
        assert client.get("/api/regions").status_code == 401
        login(client)
        response = client.get("/api/regions")

    assert response.status_code == 200
    assert len(response.json()) == 36
    assert response.json()[0] == {
        "code": "111000000",
        "name": "北京",
        "region_code": "11000000",
    }


def test_calendar_api_returns_official_text_and_source_status(tmp_path: Path) -> None:
    source = FakeTaxSource()
    with make_client(tmp_path, source) as client:
        login(client)
        response = client.get(
            "/api/calendar",
            params={"region_code": "111000000", "month": "2026-07"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["official_events"][0]["bssz"] == "申报缴纳增值税、消费税"
    assert body["official_events"][0]["start_date"] == "2026-07-01"
    assert body["stale"] is False
    assert body["sync_status"] == "fresh"
    assert body["source_url"].startswith("https://12366.chinatax.gov.cn/")


def test_calendar_api_rejects_unknown_regions_and_invalid_months(tmp_path: Path) -> None:
    source = FakeTaxSource()
    with make_client(tmp_path, source) as client:
        login(client)
        unknown = client.get(
            "/api/calendar",
            params={"region_code": "not-a-region", "month": "2026-07"},
        )
        invalid_month = client.get(
            "/api/calendar",
            params={"region_code": "111000000", "month": "2026-13"},
        )

    assert unknown.status_code == 422
    assert unknown.json()["code"] == "invalid_region"
    assert invalid_month.status_code == 422
    assert invalid_month.json()["code"] == "invalid_month"


def test_no_cache_upstream_failure_returns_503_without_diagnostics(tmp_path: Path) -> None:
    source = FakeTaxSource()
    source.error = TaxSourceUnavailableError("secret upstream response")
    with make_client(tmp_path, source) as client:
        login(client)
        response = client.get(
            "/api/calendar",
            params={"region_code": "111000000", "month": "2026-07"},
        )

    assert response.status_code == 503
    assert response.json()["code"] == "calendar_unavailable"
    assert "secret upstream response" not in response.text


def test_manual_sync_waits_for_the_selected_month(tmp_path: Path) -> None:
    source = FakeTaxSource()
    with make_client(tmp_path, source) as client:
        login(client)
        response = client.post(
            "/api/tools/tax/sync",
            json={"region_code": "111000000", "month": "2026-07"},
        )

    assert response.status_code == 200
    assert response.json()["sync_status"] == "fresh"
    assert source.call_count == 1
