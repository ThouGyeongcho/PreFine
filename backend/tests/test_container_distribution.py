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


def _publish_workflow() -> str:
    return (ROOT / ".github" / "workflows" / "publish-container.yml").read_text(
        encoding="utf-8"
    )


def _validator_pattern(workflow: str) -> str:
    validator = re.search(
        r'^\s*\[\[ "\$GITHUB_REF" =~ (?P<pattern>.+) \]\]$', workflow, re.MULTILINE
    )
    assert validator is not None
    return validator.group("pattern")


def test_publish_workflow_is_pinned_and_multi_architecture() -> None:
    workflow = _publish_workflow()

    permissions = re.search(
        r"^permissions:\n(?P<mapping>(?:^  [^\n]+\n)+)", workflow, re.MULTILINE
    )
    assert permissions is not None
    assert permissions.group("mapping") == "  contents: read\n  packages: write\n"

    expected_action_refs = [
        ("actions/checkout", "3d3c42e5aac5ba805825da76410c181273ba90b1"),
        ("docker/setup-qemu-action", "96fe6ef7f33517b61c61be40b68a1882f3264fb8"),
        ("docker/setup-buildx-action", "bb05f3f5519dd87d3ba754cc423b652a5edd6d2c"),
        ("docker/login-action", "af1e73f918a031802d376d3c8bbc3fe56130a9b0"),
        ("docker/metadata-action", "dc802804100637a589fabce1cb79ff13a1411302"),
        ("docker/build-push-action", "53b7df96c91f9c12dcc8a07bcb9ccacbed38856a"),
    ]
    actual_action_refs = re.findall(
        r"^\s*uses:\s*([^@\s]+)@([^\s#]+)", workflow, re.MULTILINE
    )
    assert actual_action_refs == expected_action_refs
    assert all(re.fullmatch(r"[0-9a-f]{40}", sha) for _, sha in actual_action_refs)

    assert "linux/amd64,linux/arm64" in workflow
    assert "ghcr.io/thougyeongcho/prefine" in workflow
    assert (
        "    if: github.event_name != 'workflow_dispatch' || github.ref == "
        "'refs/heads/main'"
    ) in workflow

    metadata = re.search(
        r"^      - name: Generate image metadata\n(?P<step>.*?)"
        r"(?=^      - name: Build and push image\n)",
        workflow,
        re.MULTILINE | re.DOTALL,
    )
    assert metadata is not None
    metadata_step = metadata.group("step")
    assert "          flavor: latest=false" in metadata_step
    tags = re.search(
        r"^          tags: \|\n(?P<rules>(?:^            .+\n)+)",
        metadata_step,
        re.MULTILINE,
    )
    assert tags is not None
    assert tags.group("rules").splitlines() == [
        "            type=raw,value=latest,enable=${{ github.ref == 'refs/heads/main' }}",
        "            type=semver,pattern={{version}},"
        "enable=${{ startsWith(github.ref, 'refs/tags/v') }}",
    ]
    assert "pattern={{major}}" not in workflow
    assert "pattern={{major}}.{{minor}}" not in workflow

    build = re.search(
        r"^      - name: Build and push image\n(?P<step>.*?)"
        r"(?=^      - name: Verify multi-architecture manifest\n)",
        workflow,
        re.MULTILINE | re.DOTALL,
    )
    assert build is not None
    build_step = build.group("step")
    for setting in (
        "          platforms: linux/amd64,linux/arm64",
        "          cache-from: type=gha",
        "          cache-to: type=gha,mode=max",
        "          provenance: mode=max",
        "          sbom: true",
    ):
        assert setting in build_step

    manifest = re.search(
        r"^      - name: Verify multi-architecture manifest\n(?P<step>.*)$",
        workflow,
        re.MULTILINE | re.DOTALL,
    )
    assert manifest is not None
    manifest_step = manifest.group("step")
    assert "docker buildx imagetools inspect" in manifest_step
    assert "grep -q 'linux/amd64'" in manifest_step
    assert "grep -q 'linux/arm64'" in manifest_step

    validation_offset = workflow.index("      - name: Validate publication ref")
    for action_name in (
        "      - name: Set up QEMU",
        "      - name: Set up Docker Buildx",
        "      - name: Log in to GHCR",
        "      - name: Build and push image",
    ):
        assert validation_offset < workflow.index(action_name)


def test_publish_workflow_validator_accepts_only_canonical_version_tags() -> None:
    validator = re.compile(_validator_pattern(_publish_workflow()))

    for ref in (
        "refs/tags/v0.1.0",
        "refs/tags/v1.0.0",
        "refs/tags/v123.456.789",
    ):
        assert validator.fullmatch(ref)

    for ref in (
        "refs/tags/v01.2.3",
        "refs/tags/v1.02.3",
        "refs/tags/v1.2.03",
        "refs/tags/v1.2.3-rc.1",
        "refs/tags/v1.2.3+build.4",
        "refs/tags/v1.2",
        "refs/tags/v1.2.3.4",
        "refs/tags/v1.2.x",
    ):
        assert not validator.fullmatch(ref)
