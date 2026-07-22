from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.tests.http_helpers import SAME_ORIGIN_HEADERS


def make_client(data_dir: Path) -> TestClient:
    settings = Settings(
        ADMIN_USERNAME="admin",
        ADMIN_PASSWORD="correct horse battery staple",
        SESSION_SECRET="0123456789abcdef0123456789abcdef",
        DATA_DIR=data_dir,
    )
    return TestClient(create_app(settings, start_scheduler=False))


def login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "correct horse battery staple"},
    )
    assert response.status_code == 204


def test_money_api_requires_authentication(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.post("/api/money/to-uppercase", json={"amount": "1.00"})

    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"


def test_to_uppercase_api_returns_the_canonical_example(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client)
        response = client.post(
            "/api/money/to-uppercase",
            headers=SAME_ORIGIN_HEADERS,
            json={"amount": "-128650.32"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "amount": "-128650.32",
        "uppercase": "负壹拾贰万捌仟陆佰伍拾元叁角贰分",
        "grouped": "-128,650.32",
        "quick_read": "-12万8650.32",
        "english": (
            "Negative one hundred twenty-eight thousand six hundred fifty yuan "
            "and thirty-two fen only"
        ),
        "normalization_note": None,
    }


def test_to_number_api_returns_all_presentations(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client)
        response = client.post(
            "/api/money/to-number",
            headers=SAME_ORIGIN_HEADERS,
            json={"uppercase": "负壹拾贰万捌仟陆佰伍拾元叁角贰分"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "amount": "-128650.32",
        "uppercase": "负壹拾贰万捌仟陆佰伍拾元叁角贰分",
        "grouped": "-128,650.32",
        "quick_read": "-12万8650.32",
        "english": (
            "Negative one hundred twenty-eight thousand six hundred fifty yuan "
            "and thirty-two fen only"
        ),
        "normalization_note": None,
    }


def test_to_number_api_normalizes_round_and_explains_standard_yuan(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client)
        response = client.post(
            "/api/money/to-number",
            headers=SAME_ORIGIN_HEADERS,
            json={"uppercase": "壹佰圆整"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "amount": "100.00",
        "uppercase": "壹佰元整",
        "grouped": "100",
        "quick_read": "100",
        "english": "One hundred yuan only",
        "normalization_note": "已按标准写法转换：“圆”应写作“元”。",
    }


def test_three_decimal_places_return_the_stable_error_shape(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client)
        response = client.post(
            "/api/money/to-uppercase",
            json={"amount": "1.001"},
            headers=SAME_ORIGIN_HEADERS,
        )

    assert response.status_code == 422
    assert response.json() == {
        "code": "invalid_money_format",
        "message": "金额最多保留两位小数。",
        "details": {},
    }


def test_authenticated_state_change_rejects_a_foreign_origin(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client)
        response = client.post(
            "/api/money/to-uppercase",
            json={"amount": "1.00"},
            headers={"Origin": "https://attacker.example"},
        )

    assert response.status_code == 403
    assert response.json()["code"] == "origin_not_allowed"


def test_browser_state_change_cannot_bypass_origin_check_by_omitting_origin(
    tmp_path: Path,
) -> None:
    with make_client(tmp_path) as client:
        login(client)
        response = client.post(
            "/api/money/to-uppercase",
            json={"amount": "1.00"},
            headers={"Sec-Fetch-Site": "cross-site"},
        )

    assert response.status_code == 403
    assert response.json()["code"] == "origin_not_allowed"


def test_request_validation_uses_the_stable_error_shape(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client)
        response = client.post("/api/money/to-uppercase", json={}, headers=SAME_ORIGIN_HEADERS)

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert response.json()["message"] == "请求参数不完整或格式不正确"
    assert response.json()["details"]["fields"] == ["amount"]
