from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = "./data"
DATA_DIR_VARIABLE = "PREFINE_DATA_DIR"


def _data_dir_from_effective_environment(environment: list[str]) -> str:
    for line in environment:
        name, separator, value = line.partition("=")
        if separator and name == DATA_DIR_VARIABLE:
            return value or DEFAULT_DATA_DIR
    return DEFAULT_DATA_DIR


def test_compose_pulls_prefine_and_mounts_only_the_host_directory() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    expected_volume_section = (
        "    volumes:\n"
        '      - "${PREFINE_DATA_DIR:-./data}:/data"\n'
    )

    assert "build:" not in compose
    assert "image: ghcr.io/thougyeongcho/prefine:${PREFINE_VERSION:-latest}" in compose
    assert "pull_policy: always" in compose
    assert 'PUID: "${PUID:-1000}"' in compose
    assert 'PGID: "${PGID:-1000}"' in compose
    assert compose.count("    volumes:\n") == 1
    assert expected_volume_section in compose
    assert "\nvolumes:\n" not in compose

    lines = compose.splitlines()
    volume_heading = lines.index("    volumes:")
    volume_entries: list[str] = []
    for line in lines[volume_heading + 1 :]:
        if not line.startswith("      "):
            break
        volume_entries.append(line)
    assert volume_entries == ['      - "${PREFINE_DATA_DIR:-./data}:/data"']


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


def test_effective_environment_parser_preserves_paths_and_falls_back() -> None:
    cases = (
        ([], DEFAULT_DATA_DIR),
        (["PREFINE_VERSION=latest", "PREFINE_DATA_DIR="], DEFAULT_DATA_DIR),
        (
            ["PREFINE_DATA_DIR=/srv/PreFine Data/tenant=a=b"],
            "/srv/PreFine Data/tenant=a=b",
        ),
        (
            [r"PREFINE_DATA_DIR=C:\PreFine Data\tenant=a=b"],
            r"C:\PreFine Data\tenant=a=b",
        ),
    )

    for environment, expected_data_dir in cases:
        assert _data_dir_from_effective_environment(environment) == expected_data_dir


def test_backup_docs_extract_the_effective_data_directory_for_each_shell() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    operations = (ROOT / "docs" / "operations.md").read_text(encoding="utf-8")
    posix_resolution = '''prefine_data_dir="$(
  docker compose config --environment |
    awk -F= '$1 == "PREFINE_DATA_DIR" { print substr($0, index($0, "=") + 1); exit }'
)"
if [ -z "$prefine_data_dir" ]; then
  prefine_data_dir="./data"
fi'''
    powershell_resolution = '''$prefineDataDirLine = docker compose config --environment |
  Where-Object { $_ -like "PREFINE_DATA_DIR=*" } |
  Select-Object -First 1
if ($prefineDataDirLine) {
  $prefineDataDir = $prefineDataDirLine.Substring($prefineDataDirLine.IndexOf("=") + 1)
}
if ([string]::IsNullOrEmpty($prefineDataDir)) {
  $prefineDataDir = ".\\data"
}'''

    assert operations.count(posix_resolution) == 2
    assert operations.count(powershell_resolution) == 2
    assert "awk -F= '{ print $2 }'" not in operations
    assert "-split '='" not in operations
    assert "-split \"=\"" not in operations
    assert '''mkdir -p "$backup_dir"
cp "$prefine_data_dir/prefine.db" "$backup_dir/prefine.db"''' in operations
    assert 'cp "$backup_dir/prefine.db" "$prefine_data_dir/prefine.db"' in operations
    backup_copy = (
        'Copy-Item -LiteralPath (Join-Path -Path $prefineDataDir '
        '-ChildPath "prefine.db") -Destination (Join-Path -Path $backupDir '
        '-ChildPath "prefine.db")'
    )
    restore_copy = (
        'Copy-Item -LiteralPath (Join-Path -Path $backupDir '
        '-ChildPath "prefine.db") -Destination (Join-Path -Path $prefineDataDir '
        '-ChildPath "prefine.db") -Force'
    )
    assert backup_copy in operations
    assert restore_copy in operations
    assert "Windows PowerShell 可将 `cp` 替换为 `Copy-Item`" not in operations
    assert readme.count("${PREFINE_DATA_DIR:-./data}") == 1


def test_publish_workflow_is_pinned_and_multi_architecture() -> None:
    workflow = (ROOT / ".github" / "workflows" / "publish-container.yml").read_text(
        encoding="utf-8"
    )

    assert "contents: read" in workflow
    assert "packages: write" in workflow
    assert "linux/amd64,linux/arm64" in workflow
    assert "ghcr.io/thougyeongcho/prefine" in workflow
    assert "type=raw,value=latest" in workflow
    assert "type=semver,pattern={{version}}" in workflow
    assert "latest=false" in workflow
    assert "cache-from: type=gha" in workflow
    assert "cache-to: type=gha,mode=max" in workflow
    assert "provenance: mode=max" in workflow
    assert "sbom: true" in workflow
    assert "imagetools inspect" in workflow
    assert "github.ref == 'refs/heads/main'" in workflow
    assert "startsWith(github.ref, 'refs/tags/v')" in workflow
    assert "@v" not in workflow

    action_refs = re.findall(r"^\s*uses:\s*[^@\s]+@([^\s#]+)", workflow, re.MULTILINE)
    assert action_refs
    assert all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in action_refs)
    assert "pattern={{major}}" not in workflow
    assert "pattern={{major}}.{{minor}}" not in workflow
