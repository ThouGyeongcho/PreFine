from __future__ import annotations

import json
import math
import re
import tomllib
from pathlib import Path

import pytest

from backend.app import __version__

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = "./data"
DATA_DIR_VARIABLE = "PREFINE_DATA_DIR"
RESTRICTED_INSPECT_FORMAT = (
    "docker inspect --format 'State={{json .State}} Health={{json .State.Health}}'"
)


def _data_dir_from_effective_environment(environment: list[str]) -> str:
    for line in environment:
        name, separator, value = line.partition("=")
        if separator and name == DATA_DIR_VARIABLE:
            return value or DEFAULT_DATA_DIR
    return DEFAULT_DATA_DIR


def _shell_function(script: str, name: str) -> str:
    function = re.search(
        rf"^{re.escape(name)}\(\) \{{\n(?P<body>.*?)(?=^\}}\n)",
        script,
        re.MULTILINE | re.DOTALL,
    )
    assert function is not None, f"missing shell function: {name}"
    return function.group("body")


def _assert_safe_smoke_diagnostic_contract(smoke_script: str) -> None:
    wait_body = _shell_function(smoke_script, "wait_for_health")
    diagnostics_body = _shell_function(smoke_script, "print_health_diagnostics")

    assert wait_body.count("curl ") == 1
    for option in ("--connect-timeout", "--max-time"):
        values = re.findall(rf"{re.escape(option)}\s+([^\s\\]+)", wait_body)
        assert len(values) == 1, f"{option} must have exactly one numeric value"
        try:
            timeout = float(values[0])
        except ValueError as error:
            raise AssertionError(f"{option} must be numeric") from error
        assert math.isfinite(timeout) and timeout > 0, f"{option} must be finite and positive"

    exhausted_timeout_path = '  done\n  print_health_diagnostics "$stage"\n  return 1\n'
    assert exhausted_timeout_path in wait_body

    inspect_calls = re.findall(r"\bdocker\s+inspect\b", smoke_script)
    assert len(inspect_calls) == 1, "smoke script must contain exactly one docker inspect"
    assert diagnostics_body.count(RESTRICTED_INSPECT_FORMAT) == 1, (
        "docker inspect must use the restricted State/Health format"
    )
    for forbidden in (
        "{{json .}}",
        ".Config",
        ".Config.Env",
        'docker inspect "$container"',
    ):
        assert forbidden not in diagnostics_body


def test_compose_pulls_prefine_and_mounts_only_the_host_directory() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    expected_volume_section = '    volumes:\n      - "${PREFINE_DATA_DIR:-./data}:/data"\n'

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


def test_readme_links_to_canonical_compose_document_without_duplicating_it() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8").strip()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "[docker-compose.yml](docker-compose.yml)" in readme
    assert f"```yaml\n{compose}\n```" not in readme


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


def test_public_documents_use_safe_credentials_and_fail_closed_maintenance() -> None:
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    security_text = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    operations = (ROOT / "docs" / "operations.md").read_text(encoding="utf-8")

    assert "ADMIN_PASSWORD=CHANGE_ME_ADMIN_PASSWORD" in env_example
    assert "SESSION_SECRET=CHANGE_ME_SESSION_SECRET" in env_example
    assert "TRUSTED_PROXY_IPS=" in env_example
    assert "Copyright (c) 2026 ThouGyeongcho" in license_text
    assert "MIT License" in license_text
    assert "security/advisories/new" in security_text
    assert "python -m backend.app.database_maintenance backup" in operations
    assert (
        "python -m backend.app.database_maintenance restore prefine-20260722T120000Z.db"
    ) in operations
    assert operations.count("set -eu") >= 2
    assert '$ErrorActionPreference = "Stop"' in operations
    assert "docker compose ps --status running --services" in operations
    running_services = 'running_services="$(docker compose ps --status running --services)"'
    assert operations.count(running_services) == 2
    assert "docker compose ps --status running --services |" not in operations
    assert "Copy-Item" not in operations
    assert 'cp "$prefine_data_dir/prefine.db"' not in operations


def _publish_workflow() -> str:
    return (ROOT / ".github" / "workflows" / "publish-container.yml").read_text(encoding="utf-8")


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


def test_publish_workflow_upgrades_pip_before_auditing() -> None:
    verify_source = _workflow_job(_publish_workflow(), "verify_source")
    tool_install = _workflow_step(verify_source, "Install backend verification tools")
    backend_verification = _workflow_step(verify_source, "Verify backend")
    pip_upgrade = "python -m pip install --upgrade 'pip==26.1.2'"
    verification_tool_install = "python -m pip install '.[dev]' 'pip-audit==2.10.1'"
    pip_audit = "python -m pip_audit"

    pip_install_commands = [
        line.strip()
        for line in tool_install.splitlines()
        if line.strip().startswith("python -m pip install")
    ]
    assert pip_install_commands == [pip_upgrade, verification_tool_install]
    assert pip_audit in backend_verification
    assert (
        verify_source.index(pip_upgrade)
        < verify_source.index(verification_tool_install)
        < verify_source.index(pip_audit)
    )


def test_publish_workflow_gates_source_image_and_release_publication() -> None:
    workflow = _publish_workflow()
    validate_ref = _workflow_job(workflow, "validate_ref")
    verify_source = _workflow_job(workflow, "verify_source")
    smoke_image = _workflow_job(workflow, "smoke_image")
    image_job = _workflow_job(workflow, "publish_image")
    release_job = _workflow_job(workflow, "publish_release")

    permissions = re.search(r"^permissions:\n(?P<mapping>(?:^  [^\n]+\n)+)", workflow, re.MULTILINE)
    assert permissions is not None
    assert permissions.group("mapping") == "  contents: read\n"

    assert not re.search(r"^    if:", validate_ref, re.MULTILINE)
    dispatch_check = 'if [ "$GITHUB_EVENT_NAME" = "workflow_dispatch" ]; then'
    dispatch_main = 'test "$GITHUB_REF" = "refs/heads/main"'
    main_check = 'if [ "$GITHUB_REF" = "refs/heads/main" ]; then'
    assert dispatch_check in validate_ref
    assert dispatch_main in validate_ref
    assert (
        validate_ref.index(dispatch_check)
        < validate_ref.index(dispatch_main)
        < validate_ref.index(main_check)
    )
    assert (
        '[[ "$GITHUB_REF" =~ ^refs/tags/v(0|[1-9][0-9]*)\\.'
        r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]"
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
    assert "--notes-file RELEASE_NOTES.md" in release_job
    assert "--generate-notes" not in release_job
    assert 'notes="$(printf' not in release_job
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
        "./gitleaks git --redact --verbose --config .gitleaks.toml",
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
    actual_action_refs = re.findall(r"^\s*uses:\s*([^@\s]+)@([^\s#]+)", workflow, re.MULTILINE)
    assert actual_action_refs == expected_action_refs
    assert all(re.fullmatch(r"[0-9a-f]{40}", sha) for _, sha in actual_action_refs)
    assert "uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97" in workflow
    assert "uses: actions/setup-node@820762786026740c76f36085b0efc47a31fe5020" in workflow

    assert "linux/amd64,linux/arm64" in image_job
    assert "ghcr.io/thougyeongcho/prefine" in workflow
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

    release_step = _workflow_step(release_job, "Create synchronized GitHub Release")
    assert (
        'gh release view "$tag" --json tagName,isDraft,isPrerelease,targetCommitish'
    ) in release_step
    assert '--arg sha "$GITHUB_SHA"' in release_step
    assert ".targetCommitish == $sha" in release_step
    assert release_step.index(".targetCommitish == $sha") < release_step.index("exit 0")
    assert '--target "$GITHUB_SHA"' in release_step


def test_smoke_script_exercises_runtime_security_and_persistence_contracts() -> None:
    smoke_script = (ROOT / "docker" / "smoke-test.sh").read_text(encoding="utf-8")

    assert "set -Eeuo pipefail" in smoke_script
    assert "trap cleanup EXIT" in smoke_script
    assert 'docker rm --force "$container"' in smoke_script
    assert "awk '/^Uid:/{print $2}' /proc/1/status" in smoke_script
    assert 'test "$(docker exec "$container"' in smoke_script
    assert '"$base_url/api/health"' in smoke_script
    assert '"$base_url/api/auth/login"' in smoke_script
    assert "--request PUT" in smoke_script
    assert '"Origin: $base_url"' in smoke_script
    assert '"$base_url/api/tools/tax/settings"' in smoke_script
    assert 'docker restart "$container"' in smoke_script
    assert smoke_script.count(".reminder_days == [9,4]") == 2
    assert 'admin_password="$(openssl rand -hex 24)"' in smoke_script
    assert 'session_secret="$(openssl rand -hex 32)"' in smoke_script
    assert '--env-file "$credentials_file"' in smoke_script
    assert '--arg password "$admin_password"' in smoke_script
    assert "--data @-" in smoke_script
    assert "ci-smoke-password-2026" not in smoke_script
    assert "ci-smoke-session-secret-0123456789abcdef" not in smoke_script
    assert smoke_script.index('docker restart "$container"') < smoke_script.rindex(
        '"$base_url/api/tools/tax/settings"'
    )


def test_smoke_health_wait_is_bounded_stage_aware_and_refreshes_the_port() -> None:
    smoke_script = (ROOT / "docker" / "smoke-test.sh").read_text(encoding="utf-8")
    wait_body = _shell_function(smoke_script, "wait_for_health")
    refresh_body = _shell_function(smoke_script, "refresh_base_url")
    assert 'local stage="${1:?health stage is required}"' in wait_body
    assert "--write-out '%{http_code}'" in wait_body
    assert 'last_health_http_code="${health_http_code:-000}"' in wait_body
    assert 'last_health_body="$(cat "$health_body_file")"' in wait_body
    assert 'last_health_curl_error="$(cat "$health_error_file")"' in wait_body
    assert 'stage_marker "$stage healthy"' in wait_body

    assert 'docker port "$container" 8000/tcp' in refresh_body
    assert 'base_url="http://127.0.0.1:$port"' in refresh_body
    assert smoke_script.count("refresh_base_url") == 3
    assert "wait_for_health initial" in smoke_script
    assert "wait_for_health restart" in smoke_script
    restart = smoke_script.index('docker restart "$container"')
    assert restart < smoke_script.index("refresh_base_url", restart)
    assert smoke_script.index("refresh_base_url", restart) < smoke_script.index(
        "wait_for_health restart", restart
    )

    for marker in (
        'stage_marker "settings saved"',
        'stage_marker "restart beginning"',
        'stage_marker "restart completed"',
        'stage_marker "persistence verified"',
    ):
        assert marker in smoke_script


def test_smoke_timeout_diagnostics_are_useful_and_do_not_expose_secrets() -> None:
    smoke_script = (ROOT / "docker" / "smoke-test.sh").read_text(encoding="utf-8")
    _assert_safe_smoke_diagnostic_contract(smoke_script)
    diagnostics_body = _shell_function(smoke_script, "print_health_diagnostics")
    for diagnostic in (
        "stage=$stage",
        "$last_health_http_code",
        "$last_health_body",
        "$last_health_curl_error",
        "docker inspect --format",
        ".State",
        ".State.Health",
        'docker top "$container"',
        'docker port "$container"',
        'docker logs --timestamps "$container"',
    ):
        assert diagnostic in diagnostics_body

    for forbidden in (
        ".Config.Env",
        'docker inspect "$container"',
        "admin_password",
        "session_secret",
        "credentials_file",
        "printenv",
        "env |",
    ):
        assert forbidden not in diagnostics_body


def test_smoke_diagnostic_contract_rejects_unsafe_mutations() -> None:
    smoke_script = (ROOT / "docker" / "smoke-test.sh").read_text(encoding="utf-8")
    zero_timeout = smoke_script.replace("--max-time 5", "--max-time 0")
    whole_object_inspect = smoke_script.replace(
        "'State={{json .State}} Health={{json .State.Health}}'",
        "'{{json .}}'",
    )

    assert zero_timeout != smoke_script
    assert whole_object_inspect != smoke_script
    with pytest.raises(AssertionError, match="--max-time must be finite and positive"):
        _assert_safe_smoke_diagnostic_contract(zero_timeout)
    with pytest.raises(AssertionError, match="restricted State/Health format"):
        _assert_safe_smoke_diagnostic_contract(whole_object_inspect)


def test_smoke_script_installs_cleanup_before_creating_credentials() -> None:
    smoke_script = (ROOT / "docker" / "smoke-test.sh").read_text(encoding="utf-8")
    temporary_directory = 'smoke_dir="$(mktemp -d'
    cleanup_trap = "trap cleanup EXIT"
    random_password = 'admin_password="$(openssl rand -hex 24)"'
    random_session_secret = 'session_secret="$(openssl rand -hex 32)"'
    credentials_write = '>"$credentials_file"'
    immediate_trap = (
        'smoke_dir="$(mktemp -d "${RUNNER_TEMP:-/tmp}/prefine-smoke.XXXXXX")"\ntrap cleanup EXIT'
    )

    assert immediate_trap in smoke_script
    assert (
        smoke_script.index(temporary_directory)
        < smoke_script.index(cleanup_trap)
        < smoke_script.index(random_password)
    )
    assert (
        smoke_script.index(cleanup_trap)
        < smoke_script.index(random_session_secret)
        < smoke_script.index(credentials_write)
    )
    assert 'if [ -n "${container:-}" ]; then' in smoke_script


def test_publish_release_binds_existing_and_new_releases_to_the_run_commit() -> None:
    release_job = _workflow_job(_publish_workflow(), "publish_release")
    release_step = _workflow_step(release_job, "Create synchronized GitHub Release")
    release_lookup = 'gh release view "$tag" --json tagName,isDraft,isPrerelease,targetCommitish'

    assert release_lookup in release_step
    assert '--arg sha "$GITHUB_SHA"' in release_step
    assert ".targetCommitish == $sha" in release_step
    assert (
        release_step.index(release_lookup)
        < release_step.index(".targetCommitish == $sha")
        < release_step.index("exit 0")
    )
    assert '--target "$GITHUB_SHA"' in release_step
    assert (
        release_step.index(".targetCommitish == $sha")
        < release_step.index("gh release create")
        < release_step.index('--target "$GITHUB_SHA"')
    )


def test_release_notes_only_describe_v0_1_2() -> None:
    release_notes = (ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")

    assert release_notes.startswith("# PreFine v0.1.2\n")
    assert "v0.1.1" not in release_notes
    assert "## Docker" not in release_notes


def test_application_version_sources_match_v0_1_2() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    frontend_package = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))

    assert {
        __version__,
        pyproject["project"]["version"],
        frontend_package["version"],
    } == {"0.1.2"}


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
    assert (
        entrypoint.index('chown -R "$puid:$pgid" /data')
        < entrypoint.index(command_dispatch)
        < entrypoint.index("python -m alembic")
    )
