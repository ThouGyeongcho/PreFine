from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.reminders import EmailDeliveryError
from backend.tests.http_helpers import SAME_ORIGIN_HEADERS


class FakeSender:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []
        self.error: Exception | None = None

    async def send(self, subject: str, body: str) -> None:
        if self.error:
            raise self.error
        self.messages.append((subject, body))


def settings(data_dir: Path, *, email: bool) -> Settings:
    values: dict[str, object] = {
        "ADMIN_USERNAME": "admin",
        "ADMIN_PASSWORD": "correct horse battery staple",
        "SESSION_SECRET": "0123456789abcdef0123456789abcdef",
        "DATA_DIR": data_dir,
    }
    if email:
        values.update(
            {
                "SMTP_HOST": "smtp.example.test",
                "SMTP_PORT": 587,
                "SMTP_FROM": "finance@example.test",
                "REMINDER_TO_EMAIL": "owner@example.test",
                "SMTP_STARTTLS": True,
            }
        )
    return Settings(**values)


def login(client: TestClient) -> None:
    assert client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "correct horse battery staple"},
    ).status_code == 204


def test_test_email_is_disabled_when_smtp_is_not_configured(tmp_path: Path) -> None:
    from backend.app.main import create_app

    sender = FakeSender()
    with TestClient(
        create_app(settings(tmp_path, email=False), start_scheduler=False, email_sender=sender)
    ) as client:
        login(client)
        response = client.post("/api/tools/tax/test-email", headers=SAME_ORIGIN_HEADERS)

    assert response.status_code == 422
    assert response.json()["code"] == "smtp_not_configured"
    assert sender.messages == []


def test_test_email_sends_without_creating_a_reminder_dispatch(tmp_path: Path) -> None:
    from backend.app.main import create_app

    sender = FakeSender()
    with TestClient(
        create_app(settings(tmp_path, email=True), start_scheduler=False, email_sender=sender)
    ) as client:
        login(client)
        response = client.post("/api/tools/tax/test-email", headers=SAME_ORIGIN_HEADERS)

    assert response.status_code == 200
    assert response.json() == {"status": "sent"}
    assert sender.messages[0][0] == "[PreFine] 测试邮件"


def test_test_email_failure_does_not_expose_smtp_diagnostics(tmp_path: Path) -> None:
    from backend.app.main import create_app

    sender = FakeSender()
    sender.error = EmailDeliveryError("smtp password was rejected")
    with TestClient(
        create_app(settings(tmp_path, email=True), start_scheduler=False, email_sender=sender)
    ) as client:
        login(client)
        response = client.post("/api/tools/tax/test-email", headers=SAME_ORIGIN_HEADERS)

    assert response.status_code == 503
    assert response.json()["code"] == "email_delivery_failed"
    assert "smtp password was rejected" not in response.text
