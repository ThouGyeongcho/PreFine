from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app


def make_settings(data_dir: Path, *, cookie_secure: bool = False) -> Settings:
    return Settings(
        ADMIN_USERNAME="admin",
        ADMIN_PASSWORD="correct horse battery staple",
        SESSION_SECRET="0123456789abcdef0123456789abcdef",
        DATA_DIR=data_dir,
        COOKIE_SECURE=cookie_secure,
    )


def make_client(
    data_dir: Path,
    *,
    auth_now: Callable[[], datetime] | None = None,
    cookie_secure: bool = False,
) -> TestClient:
    app = create_app(
        make_settings(data_dir, cookie_secure=cookie_secure),
        start_scheduler=False,
        auth_now=auth_now,
    )
    return TestClient(app)


def test_login_sets_a_twelve_hour_http_only_same_site_cookie(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "correct horse battery staple"},
        )

    assert response.status_code == 204
    cookie = response.headers["set-cookie"]
    assert "prefine_session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Max-Age=43200" in cookie
    assert "Secure" not in cookie


def test_secure_cookie_setting_is_respected(tmp_path: Path) -> None:
    with make_client(tmp_path, cookie_secure=True) as client:
        response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "correct horse battery staple"},
        )

    assert "Secure" in response.headers["set-cookie"]


def test_wrong_credentials_return_a_stable_error_without_a_cookie(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong"},
        )

    assert response.status_code == 401
    assert response.json() == {
        "code": "invalid_credentials",
        "message": "用户名或密码错误",
        "details": {},
    }
    assert "set-cookie" not in response.headers


def test_sixth_failed_login_within_fifteen_minutes_is_rate_limited(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        for _ in range(5):
            response = client.post(
                "/api/auth/login",
                json={"username": "admin", "password": "wrong"},
            )
            assert response.status_code == 401

        blocked = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong"},
        )

    assert blocked.status_code == 429
    assert blocked.json()["code"] == "login_rate_limited"


def test_successful_login_clears_the_ip_failure_counter(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        for _ in range(4):
            client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})

        success = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "correct horse battery staple"},
        )
        client.post("/api/auth/logout")
        after_reset = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong"},
        )

    assert success.status_code == 204
    assert after_reset.status_code == 401


def test_session_expires_after_twelve_hours(tmp_path: Path) -> None:
    current = [datetime(2026, 7, 21, 1, 0, tzinfo=UTC)]

    with make_client(tmp_path, auth_now=lambda: current[0]) as client:
        assert client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "correct horse battery staple"},
        ).status_code == 204
        assert client.get("/api/auth/me").status_code == 200

        current[0] += timedelta(hours=12, seconds=1)
        expired = client.get("/api/auth/me")

    assert expired.status_code == 401
    assert expired.json()["code"] == "authentication_required"


def test_logout_rejects_a_foreign_origin(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "correct horse battery staple"},
        )
        response = client.post(
            "/api/auth/logout",
            headers={"Origin": "https://attacker.example"},
        )

    assert response.status_code == 403
    assert response.json()["code"] == "origin_not_allowed"


def test_logout_clears_the_session(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "correct horse battery staple"},
        )
        response = client.post("/api/auth/logout")
        me = client.get("/api/auth/me")

    assert response.status_code == 204
    assert me.status_code == 401
