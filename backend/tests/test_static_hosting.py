from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app


def make_settings(data_dir: Path) -> Settings:
    return Settings(
        ADMIN_USERNAME="admin",
        ADMIN_PASSWORD="correct horse battery staple",
        SESSION_SECRET="0123456789abcdef0123456789abcdef",
        DATA_DIR=data_dir,
    )


def test_spa_routes_and_assets_are_served_without_shadowing_api(tmp_path: Path) -> None:
    static_dir = tmp_path / "dist"
    assets_dir = static_dir / "assets"
    assets_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text(
        '<!doctype html><div id="root">PreFine shell</div>',
        encoding="utf-8",
    )
    (assets_dir / "app.js").write_text("window.preFine = true", encoding="utf-8")
    app = create_app(
        make_settings(tmp_path / "data"),
        start_scheduler=False,
        static_dir=static_dir,
    )

    with TestClient(app) as client:
        root = client.get("/")
        nested = client.get("/calendar")
        asset = client.get("/assets/app.js")
        unknown_api = client.get("/api/not-a-real-route")

    assert root.status_code == 200
    assert "PreFine shell" in root.text
    assert nested.status_code == 200
    assert "PreFine shell" in nested.text
    assert asset.status_code == 200
    assert asset.text == "window.preFine = true"
    assert unknown_api.status_code == 404
    assert unknown_api.headers["content-type"].startswith("application/json")
    assert unknown_api.json() == {
        "code": "not_found",
        "message": "请求的资源不存在",
        "details": {},
    }


def test_api_starts_when_frontend_build_is_absent(tmp_path: Path) -> None:
    app = create_app(
        make_settings(tmp_path / "data"),
        start_scheduler=False,
        static_dir=tmp_path / "missing-dist",
    )

    with TestClient(app) as client:
        health = client.get("/api/health")
        root = client.get("/")

    assert health.status_code == 200
    assert root.status_code == 404
