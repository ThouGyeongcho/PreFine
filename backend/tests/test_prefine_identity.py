from __future__ import annotations

import hashlib
from pathlib import Path

from backend.app.auth import SESSION_COOKIE, SESSION_SALT
from backend.app.config import Settings

ROOT = Path(__file__).resolve().parents[2]
FINAL_LOGO = ROOT / "assets" / "branding" / "prefine-logo-512.png"
EXPECTED_LOGO_SHA256 = "ac9901d5c3dac3d3b67b287f2d63c050465066c609aa269ec619200409992df7"
SKIPPED_DIRECTORIES = {
    ".git",
    ".pnpm-store",
    ".pytest_cache",
    ".ruff_cache",
    ".superpowers",
    ".test-tmp",
    ".venv",
    "__pycache__",
    "dist",
    "node_modules",
    "playwright-report",
    "test-results",
}
TEXT_SUFFIXES = {
    "",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
}


def _current_text_files() -> list[Path]:
    result: list[Path] = []
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if any(
            part in SKIPPED_DIRECTORIES or part.startswith("pytest-cache-files-")
            for part in relative.parts
        ):
            continue
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
            result.append(path)
    return result


def test_runtime_identity_uses_prefine_names(tmp_path: Path) -> None:
    settings = Settings(
        ADMIN_USERNAME="admin",
        ADMIN_PASSWORD="test-password",
        SESSION_SECRET="0123456789abcdef0123456789abcdef",
        DATA_DIR=tmp_path,
    )

    assert settings.database_path == tmp_path / "prefine.db"
    assert SESSION_COOKIE == "prefine_session"
    assert SESSION_SALT == "prefine-session-v1"


def test_current_tree_contains_no_legacy_project_identifier() -> None:
    legacy_slug = "finance" + "-" + "toolkit"
    legacy_title = "Finance" + " " + "Toolkit"
    condensed_legacy_title = "Finance" + "Toolkit"
    former_chinese_title = "财务" + "工具包"
    mixed_case_identifier = "pre" + "Fine"
    findings: list[str] = []

    for path in _current_text_files():
        relative = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        if (
            legacy_slug in relative.lower()
            or legacy_slug in text.lower()
            or legacy_title in text
            or condensed_legacy_title in text
            or former_chinese_title in text
            or mixed_case_identifier in text
        ):
            findings.append(relative)

    assert findings == []


def test_only_the_confirmed_logo_is_present() -> None:
    branding_files = sorted(path.name for path in FINAL_LOGO.parent.glob("*.png"))
    assert branding_files == [FINAL_LOGO.name]
    assert hashlib.sha256(FINAL_LOGO.read_bytes()).hexdigest() == EXPECTED_LOGO_SHA256
