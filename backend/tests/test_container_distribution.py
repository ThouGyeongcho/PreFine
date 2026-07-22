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


def _workflow_job(workflow: str, name: str) -> str:
    job = re.search(
        rf"^  {re.escape(name)}:\n(?P<body>.*?)(?=^  [a-z_]+:\n|\Z)",
        workflow,
        re.MULTILINE | re.DOTALL,
    )
    assert job is not None
    return job.group("body")


def _workflow_step(job: str, name: str) -> str:
    step = re.search(
        rf"^      - name: {re.escape(name)}\n(?P<body>.*?)(?=^      - name:|\Z)",
        job,
        re.MULTILINE | re.DOTALL,
    )
    assert step is not None
    return step.group("body")


def test_publish_workflow_gates_source_image_and_release_publication() -> None:
    workflow = _publish_workflow()
    validate_ref = _workflow_job(workflow, "validate_ref")
    verify_source = _workflow_job(workflow, "verify_source")
    smoke_image = _workflow_job(workflow, "smoke_image")
    image_job = _workflow_job(workflow, "publish_image")
    release_job = _workflow_job(workflow, "publish_release")

    permissions = re.search(
        r"^permissions:\n(?P<mapping>(?:^  [^\n]+\n)+)", workflow, re.MULTILINE
    )
    assert permissions is not None
    assert permissions.group("mapping") == "  contents: read\n"

    assert (
        "if: github.event_name != 'workflow_dispatch' || github.ref == "
        "'refs/heads/main'"
    ) in validate_ref
    assert (
        '[[ "$GITHUB_REF" =~ ^refs/tags/v(0|[1-9][0-9]*)\\.'
        r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]'
    ) in validate_ref
    assert "needs: validate_ref" in verify_source
    assert "needs: verify_source" in smoke_image
    assert "needs: smoke_image" in image_job
    assert "needs: publish_image" in release_job
    assert workflow.index("needs: verify_source") < workflow.index("needs: smoke_image")
    assert workflow.index("Verify multi-architecture manifest") < workflow.index(
        "gh release create"
    )

    assert "permissions:\n      contents: read\n      packages: write" in image_job
    assert "permissions:\n      contents: write" in release_job
    assert "--verify-tag" in release_job
    assert "--generate-notes" in release_job
    assert "if: startsWith(github.ref, 'refs/tags/v')" in release_job

    source_checkout = _workflow_step(verify_source, "Check out complete history")
    assert "fetch-depth: 0" in source_checkout

    backend_verification = _workflow_step(verify_source, "Verify backend")
    for source_gate in (
        "python -m pytest backend/tests",
        "python -m ruff check backend",
        "python -m pip_audit",
    ):
        assert source_gate in backend_verification

    frontend_verification = _workflow_step(verify_source, "Audit and verify frontend")
    frontend_commands = [
        line.strip()
        for line in frontend_verification.splitlines()
        if line.strip().startswith("pnpm --dir frontend")
    ]
    assert frontend_commands == [
        "pnpm --dir frontend audit --prod --audit-level high",
        "pnpm --dir frontend run lint",
        "pnpm --dir frontend exec vitest run",
        "pnpm --dir frontend run build",
        "pnpm --dir frontend exec playwright install --with-deps chromium",
        "pnpm --dir frontend exec playwright test",
    ]

    gitleaks = _workflow_step(verify_source, "Scan complete history for secrets")
    for command in (
        'curl --fail --silent --show-error --location --remote-name "$base/$archive"',
        'curl --fail --silent --show-error --location --remote-name "$base/$checksums"',
        'grep "  $archive$" "$checksums" | sha256sum --check --strict -',
        'tar --extract --gzip --file "$archive" gitleaks',
        './gitleaks git --redact --verbose --config .gitleaks.toml',
    ):
        assert command in gitleaks
    assert gitleaks.index('"$base/$archive"') < gitleaks.index('"$base/$checksums"')
    assert gitleaks.index('"$base/$checksums"') < gitleaks.index("sha256sum")
    assert gitleaks.index("sha256sum") < gitleaks.index("tar --extract")
    assert gitleaks.index("tar --extract") < gitleaks.index("gitleaks git --redact")

    smoke_build = _workflow_step(smoke_image, "Build smoke image without pushing")
    assert "platforms: linux/amd64" in smoke_build
    assert "load: true" in smoke_build
    assert "push: false" in smoke_build
    assert "tags: prefine:smoke" in smoke_build
    assert "platforms: linux/amd64,linux/arm64" not in smoke_build
    assert "push: true" not in smoke_build
    assert "docker/login-action" not in smoke_image
    assert "docker login" not in smoke_image
    assert "docker push" not in smoke_image
    assert "docker/smoke-test.sh prefine:smoke" in smoke_image

    expected_action_refs = [
        ("actions/checkout", "3d3c42e5aac5ba805825da76410c181273ba90b1"),
        ("actions/setup-python", "5fda3b95a4ea91299a34e894583c3862153e4b97"),
        ("actions/setup-node", "820762786026740c76f36085b0efc47a31fe5020"),
        ("actions/checkout", "3d3c42e5aac5ba805825da76410c181273ba90b1"),
        ("docker/setup-buildx-action", "bb05f3f5519dd87d3ba754cc423b652a5edd6d2c"),
        ("docker/build-push-action", "53b7df96c91f9c12dcc8a07bcb9ccacbed38856a"),
        ("actions/checkout", "3d3c42e5aac5ba805825da76410c181273ba90b1"),
        ("docker/setup-qemu-action", "96fe6ef7f33517b61c61be40b68a1882f3264fb8"),
        ("docker/setup-buildx-action", "bb05f3f5519dd87d3ba754cc423b652a5edd6d2c"),
        ("docker/login-action", "af1e73f918a031802d376d3c8bbc3fe56130a9b0"),
        ("docker/metadata-action", "dc802804100637a589fabce1cb79ff13a1411302"),
        ("docker/build-push-action", "53b7df96c91f9c12dcc8a07bcb9ccacbed38856a"),
        ("actions/checkout", "3d3c42e5aac5ba805825da76410c181273ba90b1"),
    ]
    actual_action_refs = re.findall(
        r"^\s*uses:\s*([^@\s]+)@([^\s#]+)", workflow, re.MULTILINE
    )
    assert actual_action_refs == expected_action_refs
    assert all(re.fullmatch(r"[0-9a-f]{40}", sha) for _, sha in actual_action_refs)
    assert "uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97" in workflow
    assert "uses: actions/setup-node@820762786026740c76f36085b0efc47a31fe5020" in workflow

    assert "linux/amd64,linux/arm64" in image_job
    assert "ghcr.io/thougyeongcho/prefine" in workflow
    assert (
        "    if: github.event_name != 'workflow_dispatch' || github.ref == "
        "'refs/heads/main'"
    ) in workflow

    metadata = re.search(
        r"^      - name: Generate image metadata\n(?P<step>.*?)"
        r"(?=^      - name: Build and push image\n)",
        image_job,
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
    assert "pattern={{major}}" not in image_job
    assert "pattern={{major}}.{{minor}}" not in image_job

    build = re.search(
        r"^      - name: Build and push image\n(?P<step>.*?)"
        r"(?=^      - name: Verify multi-architecture manifest\n)",
        image_job,
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
        image_job,
        re.MULTILINE | re.DOTALL,
    )
    assert manifest is not None
    manifest_step = manifest.group("step")
    assert "docker buildx imagetools inspect" in manifest_step
    assert "grep -q 'linux/amd64'" in manifest_step
    assert "grep -q 'linux/arm64'" in manifest_step



def test_smoke_script_exercises_runtime_security_and_persistence_contracts() -> None:
    smoke_script = (ROOT / "docker" / "smoke-test.sh").read_text(encoding="utf-8")

    assert "set -Eeuo pipefail" in smoke_script
    assert "trap cleanup EXIT" in smoke_script
    assert "docker rm --force \"$container\"" in smoke_script
    assert "awk '/^Uid:/{print $2}' /proc/1/status" in smoke_script
    assert 'test "$(docker exec "$container"' in smoke_script
    assert '"$base_url/api/health"' in smoke_script
    assert '"$base_url/api/auth/login"' in smoke_script
    assert "--request PUT" in smoke_script
    assert '"Origin: $base_url"' in smoke_script
    assert '"$base_url/api/tools/tax/settings"' in smoke_script
    assert "docker restart \"$container\"" in smoke_script
    assert smoke_script.count(".reminder_days == [9,4]") == 2
    assert smoke_script.index("docker restart \"$container\"") < smoke_script.rindex(
        '"$base_url/api/tools/tax/settings"'
    )


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


def test_entrypoint_dispatches_maintenance_commands_after_data_preparation() -> None:
    entrypoint = (ROOT / "docker" / "entrypoint.sh").read_text(encoding="utf-8")

    command_dispatch = 'if [ "$#" -gt 0 ]; then\n  exec gosu "$puid:$pgid" "$@"\nfi'
    assert command_dispatch in entrypoint
    assert entrypoint.index('chown -R "$puid:$pgid" /data') < entrypoint.index(
        command_dispatch
    ) < entrypoint.index("python -m alembic")
