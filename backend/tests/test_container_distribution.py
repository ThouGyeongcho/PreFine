from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_compose_pulls_prefine_and_mounts_a_host_directory() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "build:" not in compose
    assert "image: ghcr.io/thougyeongcho/prefine:${PREFINE_VERSION:-latest}" in compose
    assert "pull_policy: always" in compose
    assert '${PREFINE_DATA_DIR:-./data}:/data' in compose
    assert 'PUID: "${PUID:-1000}"' in compose
    assert 'PGID: "${PGID:-1000}"' in compose


def test_readme_contains_the_exact_compose_document() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8").strip()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"```yaml\n{compose}\n```" in readme


def test_local_data_and_secrets_are_ignored() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert "/data/" in gitignore
    assert "/data" in dockerignore
    assert ".env" in gitignore
    assert ".env" in dockerignore


def test_backup_docs_resolve_the_compose_data_directory_for_each_shell() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    operations = (ROOT / "docs" / "operations.md").read_text(encoding="utf-8")

    assert "docker compose config --environment" in operations
    assert "### POSIX sh" in operations
    assert "### PowerShell" in operations
    assert "prefine_data_dir" in operations
    assert "awk -F=" in operations
    assert "$prefineDataDir" in operations
    assert "Join-Path" in operations
    assert "Copy-Item -LiteralPath" in operations
    assert "Windows PowerShell 可将 `cp` 替换为 `Copy-Item`" not in operations
    assert readme.count("${PREFINE_DATA_DIR:-./data}") == 1
