from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.tax_source import SourceCalendarEvent, YearMonth


class FakeTaxSource:
    async def fetch_month(
        self,
        region_code: str,
        month: YearMonth,
    ) -> list[SourceCalendarEvent]:
        return [
            SourceCalendarEvent(
                source_event_id="mixed-event",
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


def make_client(data_dir: Path) -> TestClient:
    settings = Settings(
        ADMIN_USERNAME="admin",
        ADMIN_PASSWORD="correct horse battery staple",
        SESSION_SECRET="0123456789abcdef0123456789abcdef",
        DATA_DIR=data_dir,
    )
    return TestClient(create_app(settings, start_scheduler=False, tax_source=FakeTaxSource()))


def login(client: TestClient) -> None:
    assert client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "correct horse battery staple"},
    ).status_code == 204


def valid_settings() -> dict[str, object]:
    return {
        "default_mode": "personalized",
        "taxpayer_type": "general_taxpayer",
        "selected_item_codes": ["vat", "corporate_income_tax"],
        "default_region_code": "111000000",
        "reminder_days": [7, 3, 1],
    }


def test_settings_default_to_an_incomplete_official_profile(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client)
        response = client.get("/api/tools/tax/settings")

    assert response.status_code == 200
    assert response.json() == {
        "default_mode": "official",
        "taxpayer_type": None,
        "selected_item_codes": [],
        "default_region_code": None,
        "reminder_days": [7, 3, 1],
        "profile_complete": False,
        "email_configured": False,
    }


def test_catalog_api_exposes_stable_selectable_items(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client)
        response = client.get("/api/tools/tax/catalog")

    assert response.status_code == 200
    items = {item["code"]: item for item in response.json()}
    assert items["vat"] == {
        "code": "vat",
        "category": "tax",
        "display_name": "增值税",
        "taxpayer_scope": ["general_taxpayer", "small_scale_taxpayer"],
    }
    assert "financial_reports" in items


def test_settings_are_transactionally_saved_and_reloaded(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client)
        saved = client.put("/api/tools/tax/settings", json=valid_settings())
        reloaded = client.get("/api/tools/tax/settings")

    assert saved.status_code == 200
    assert saved.json()["profile_complete"] is True
    assert reloaded.json() == saved.json()


def test_invalid_settings_keep_the_previous_value(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client)
        assert client.put("/api/tools/tax/settings", json=valid_settings()).status_code == 200
        invalid = valid_settings()
        invalid["reminder_days"] = [31]
        rejected = client.put("/api/tools/tax/settings", json=invalid)
        reloaded = client.get("/api/tools/tax/settings")

    assert rejected.status_code == 422
    assert reloaded.json()["reminder_days"] == [7, 3, 1]


def test_unknown_catalog_code_is_rejected_without_overwriting_settings(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client)
        assert client.put("/api/tools/tax/settings", json=valid_settings()).status_code == 200
        invalid = valid_settings()
        invalid["selected_item_codes"] = ["not-a-real-item"]
        rejected = client.put("/api/tools/tax/settings", json=invalid)
        reloaded = client.get("/api/tools/tax/settings")

    assert rejected.status_code == 422
    assert rejected.json()["code"] == "invalid_tax_item"
    assert reloaded.json()["selected_item_codes"] == ["vat", "corporate_income_tax"]


def test_calendar_returns_personalized_matches_unknowns_and_unchanged_official_text(
    tmp_path: Path,
) -> None:
    with make_client(tmp_path) as client:
        login(client)
        configured = valid_settings()
        configured["selected_item_codes"] = ["vat"]
        assert client.put("/api/tools/tax/settings", json=configured).status_code == 200
        response = client.get(
            "/api/calendar",
            params={"region_code": "111000000", "month": "2026-07"},
        )

    body = response.json()
    assert body["profile_complete"] is True
    assert body["official_events"][0]["bssz"] == "申报缴纳增值税、神秘新税种"
    assert [item["display_name"] for item in body["personalized_events"]] == [
        "增值税",
        "其他待确认",
    ]
    assert body["personalized_events"][1]["official_text"] == "申报缴纳增值税、神秘新税种"
