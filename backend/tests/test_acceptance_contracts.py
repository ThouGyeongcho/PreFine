from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.tax_source import SourceCalendarEvent, TaxSourceUnavailableError, YearMonth


class AcceptanceTaxSource:
    def __init__(self, *, unavailable: bool = False) -> None:
        self.unavailable = unavailable

    async def fetch_month(
        self,
        region_code: str,
        month: YearMonth,
    ) -> list[SourceCalendarEvent]:
        if self.unavailable:
            raise TaxSourceUnavailableError("simulated outage")
        return [
            SourceCalendarEvent(
                source_event_id="acceptance-event",
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 15),
                bssz="申报缴纳增值税、神秘新税种",
                split_items=("申报缴纳增值税", "神秘新税种"),
                source_agency="国家税务总局",
                source_created_at="2025-12-29 13:40:56",
                source_region_name="北京市税务局",
                remark="",
                source_order=0,
            )
        ]


def make_settings(data_dir: Path) -> Settings:
    return Settings(
        ADMIN_USERNAME="admin",
        ADMIN_PASSWORD="correct horse battery staple",
        SESSION_SECRET="0123456789abcdef0123456789abcdef",
        DATA_DIR=data_dir,
    )


def login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "correct horse battery staple"},
    )
    assert response.status_code == 204


def test_canonical_amount_acceptance(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), start_scheduler=False)

    with TestClient(app) as client:
        login(client)
        encoded = client.post(
            "/api/money/to-uppercase",
            json={"amount": "-128650.32"},
        )
        decoded = client.post(
            "/api/money/to-number",
            json={"uppercase": encoded.json()["uppercase"]},
        )

    assert encoded.json()["uppercase"] == "负壹拾贰万捌仟陆佰伍拾元叁角贰分"
    assert decoded.json()["amount"] == "-128650.32"


def test_restart_preserves_settings_cache_and_official_text_during_outage(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    initial_app = create_app(
        settings,
        start_scheduler=False,
        tax_source=AcceptanceTaxSource(),
    )
    official_text = "申报缴纳增值税、神秘新税种"

    with TestClient(initial_app) as client:
        login(client)
        saved = client.put(
            "/api/tools/tax/settings",
            json={
                "default_mode": "personalized",
                "taxpayer_type": "general_taxpayer",
                "selected_item_codes": ["vat"],
                "default_region_code": "111000000",
                "reminder_days": [7, 3, 1],
            },
        )
        calendar = client.get(
            "/api/calendar",
            params={"region_code": "111000000", "month": "2026-07"},
        )

    assert saved.status_code == 200
    assert calendar.json()["official_events"][0]["bssz"] == official_text
    assert {item["display_name"] for item in calendar.json()["personalized_events"]} == {
        "增值税",
        "其他待确认",
    }

    restarted_app = create_app(
        settings,
        start_scheduler=False,
        tax_source=AcceptanceTaxSource(unavailable=True),
    )
    with TestClient(restarted_app) as client:
        login(client)
        persisted = client.get("/api/tools/tax/settings")
        fallback = client.post(
            "/api/tools/tax/sync",
            json={"region_code": "111000000", "month": "2026-07"},
        )

    assert persisted.json()["selected_item_codes"] == ["vat"]
    assert fallback.status_code == 200
    assert fallback.json()["stale"] is True
    assert fallback.json()["sync_status"] == "failed_using_cache"
    assert fallback.json()["official_events"][0]["bssz"] == official_text
