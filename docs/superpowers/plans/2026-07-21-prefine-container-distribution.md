# PreFine Container Distribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename every current project identifier to PreFine, publish public amd64/arm64 GHCR images automatically, and let users run the application from a bind-mounted host directory without building locally.

**Architecture:** The runtime image starts with a minimal root entrypoint that validates PUID/PGID, prepares `/data`, and then permanently drops to the `prefine` identity before migrations and Uvicorn. GitHub Actions is the only container builder; Compose pulls `ghcr.io/thougyeongcho/prefine` and mounts `${PREFINE_DATA_DIR:-./data}`. The repository and package remain private until tests, dependency audits, secret/history scans, image build, and remote-history verification pass.

**Tech Stack:** Python 3.12, pytest, POSIX shell, Docker Compose, GitHub Actions, Buildx/QEMU, GHCR, Gitleaks 8.30.1, git-filter-repo 2.47.0

## Global Constraints

- User-facing branding is `PreFine`; every current technical identifier is lowercase `prefine`.
- The current tree must contain no contiguous legacy slug or legacy English title. Tests construct those markers from separate string fragments so the tests do not reintroduce them.
- The only published brand asset is `assets/branding/prefine-logo-512.png`, SHA-256 `AC9901D5C3DAC3D3B67B287F2D63C050465066C609AA269EC619200409992DF7`.
- Six option/contact-sheet PNGs named in the approved spec must be removed from the current tree and every public reachable commit.
- The image name is `ghcr.io/thougyeongcho/prefine`; only `latest` and exact `X.Y.Z` tags are published.
- The image platforms are exactly `linux/amd64` and `linux/arm64`.
- Compose must not contain `build`; local release work must not build a Docker image.
- Persistent data defaults to `${PREFINE_DATA_DIR:-./data}:/data`, with `PUID=1000` and `PGID=1000` defaults.
- The web service and Alembic run as non-root `prefine`; root exists only during mount preparation.
- Public visibility changes happen only after the fail-closed security gate and successful private `latest` workflow.
- Never use an unleased force push. History replacement uses the exact observed remote SHA with `--force-with-lease`.

---

### Task 1: Lock the Final Brand Asset and Rename the Current Project

**Files:**
- Create: `backend/tests/test_prefine_identity.py`
- Modify: `pyproject.toml`
- Modify: `backend/app/config.py`
- Modify: `backend/app/auth.py`
- Modify: `backend/alembic.ini`
- Modify: `backend/tests/test_health.py`
- Modify: `frontend/package.json`
- Modify: `frontend/pnpm-lock.yaml`
- Modify: `Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `docker/entrypoint.sh`
- Modify: `README.md`
- Modify: `docs/operations.md`
- Modify: `docs/superpowers/specs/2026-07-21-github-publication-design.md`
- Modify: `docs/superpowers/plans/2026-07-21-github-publication.md`
- Move: legacy V1 design filename, resolved with `$legacySlug = 'finance' + '-' + 'toolkit'`, to `docs/superpowers/specs/2026-07-21-prefine-design.md`
- Move: legacy V1 plan filename, resolved with the same `$legacySlug`, to `docs/superpowers/plans/2026-07-21-prefine-v1.md`
- Preserve: `assets/branding/prefine-logo-512.png`
- Delete: the six option/contact-sheet paths listed in `docs/superpowers/specs/2026-07-21-prefine-container-distribution-design.md`

**Interfaces:**
- Consumes: the user-confirmed logo bytes and approved naming table.
- Produces: `Settings.database_path == DATA_DIR / "prefine.db"`, `SESSION_SALT == "prefine-session-v1"`, package names `prefine` and `prefine-frontend`, and a current tree containing only PreFine identifiers.

- [ ] **Step 1: Write the failing identity and asset contract**

Create `backend/tests/test_prefine_identity.py`:

```python
from __future__ import annotations

import hashlib
from pathlib import Path

from backend.app.auth import SESSION_SALT
from backend.app.config import Settings


ROOT = Path(__file__).resolve().parents[2]
FINAL_LOGO = ROOT / "assets" / "branding" / "prefine-logo-512.png"
EXPECTED_LOGO_SHA256 = "ac9901d5c3dac3d3b67b287f2d63c050465066c609aa269ec619200409992df7"
SKIPPED_DIRECTORIES = {
    ".git",
    ".pnpm-store",
    ".pytest_cache",
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
        if any(part in SKIPPED_DIRECTORIES or part.startswith("pytest-cache-files-") for part in relative.parts):
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
    assert SESSION_SALT == "prefine-session-v1"


def test_current_tree_contains_no_legacy_project_identifier() -> None:
    legacy_slug = "finance" + "-" + "toolkit"
    legacy_title = "Finance" + " " + "Toolkit"
    findings: list[str] = []

    for path in _current_text_files():
        relative = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        if legacy_slug in relative.lower() or legacy_slug in text.lower() or legacy_title in text:
            findings.append(relative)

    assert findings == []


def test_only_the_confirmed_logo_is_present() -> None:
    branding_files = sorted(path.name for path in FINAL_LOGO.parent.glob("*.png"))
    assert branding_files == [FINAL_LOGO.name]
    assert hashlib.sha256(FINAL_LOGO.read_bytes()).hexdigest() == EXPECTED_LOGO_SHA256
```

- [ ] **Step 2: Run the contract to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_prefine_identity.py -v
```

Expected: import fails because `SESSION_SALT` is not exported, or assertions fail on legacy names and extra PNGs.

- [ ] **Step 3: Apply the exact identity changes**

Make these source changes:

```python
# backend/app/auth.py
SESSION_SALT = "prefine-session-v1"

# URLSafeSerializer(...)
salt=SESSION_SALT
```

```python
# backend/app/config.py
return self.data_dir / "prefine.db"
```

Make these metadata/configuration replacements:

```text
pyproject.toml project.name: prefine
pyproject.toml project.description: PreFine for mainland China finance teams
frontend/package.json name: prefine-frontend
backend/alembic.ini database URL: sqlite+pysqlite:////data/prefine.db
backend/tests/test_health.py expected startup database: prefine.db
```

Rename the two legacy design/plan files without writing the legacy slug into a new tracked file:

```powershell
$legacySlug = 'finance' + '-' + 'toolkit'
git mv "docs/superpowers/specs/2026-07-21-$legacySlug-design.md" "docs/superpowers/specs/2026-07-21-prefine-design.md"
git mv "docs/superpowers/plans/2026-07-21-$legacySlug-v1.md" "docs/superpowers/plans/2026-07-21-prefine-v1.md"
```

Update the renamed documents, README, operations guide, publication design, publication plan, package lock, Docker-related files, and comments so product prose uses `PreFine` and technical prose uses `prefine`. Remove the six process PNGs with exact path-scoped `git rm`; do not delete or replace the final logo.

Before the later container tasks, apply these mechanical Docker-name replacements so the global current-tree contract can pass:

```text
Dockerfile user/group: prefine
Dockerfile entrypoint path: /usr/local/bin/prefine-entrypoint
docker-compose.yml temporary local image name: prefine:0.1.0
docker-compose.yml temporary named volume: prefine-data
```

- [ ] **Step 4: Verify the identity contract passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_prefine_identity.py backend/tests/test_health.py -v
.\.venv\Scripts\python.exe -m ruff check backend
```

Expected: all selected tests pass and Ruff reports `All checks passed!`.

- [ ] **Step 5: Commit the identity and final asset**

Run:

```powershell
git add pyproject.toml backend frontend README.md docs assets/branding Dockerfile docker-compose.yml docker/entrypoint.sh
git diff --cached --check
git commit -m "refactor: rename project to prefine"
```

Expected: the final Logo update, identity changes, document renames, and six current-tree deletions are committed together.

### Task 2: Validate PUID/PGID and Drop Container Privileges

**Files:**
- Create: `backend/app/container_identity.py`
- Create: `backend/tests/test_container_identity.py`
- Modify: `docker/entrypoint.sh`
- Modify: `Dockerfile`

**Interfaces:**
- Consumes: environment variables `PUID` and `PGID`, each defaulting to decimal `1000`.
- Produces: `ContainerIdentity(uid: int, gid: int)`, CLI output `<uid>:<gid>`, exit code `64` for invalid IDs, root-only mount preparation, and a final `gosu <uid>:<gid>` process.

- [ ] **Step 1: Write failing PUID/PGID tests**

Create `backend/tests/test_container_identity.py`:

```python
from __future__ import annotations

import pytest

from backend.app.container_identity import ContainerIdentity, parse_positive_id


def test_container_identity_defaults_to_uid_and_gid_1000(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PUID", raising=False)
    monkeypatch.delenv("PGID", raising=False)
    assert ContainerIdentity.from_environment() == ContainerIdentity(uid=1000, gid=1000)


@pytest.mark.parametrize("raw", ["", "0", "-1", "1.5", "abc", "１２３"])
def test_container_identity_rejects_invalid_values(raw: str) -> None:
    with pytest.raises(ValueError, match="positive ASCII decimal integer"):
        parse_positive_id("PUID", raw)


def test_container_identity_accepts_positive_ascii_decimal_values() -> None:
    assert parse_positive_id("PGID", "1001") == 1001
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_container_identity.py -v
```

Expected: FAIL because `backend.app.container_identity` does not exist.

- [ ] **Step 3: Implement the identity parser**

Create `backend/app/container_identity.py`:

```python
from __future__ import annotations

import os
import sys
from dataclasses import dataclass


def parse_positive_id(name: str, raw: str) -> int:
    if not raw or not raw.isascii() or not raw.isdecimal() or int(raw) == 0:
        raise ValueError(f"{name} must be a positive ASCII decimal integer")
    return int(raw)


@dataclass(frozen=True, slots=True)
class ContainerIdentity:
    uid: int
    gid: int

    @classmethod
    def from_environment(cls) -> "ContainerIdentity":
        return cls(
            uid=parse_positive_id("PUID", os.getenv("PUID", "1000")),
            gid=parse_positive_id("PGID", os.getenv("PGID", "1000")),
        )


def main() -> int:
    try:
        identity = ContainerIdentity.from_environment()
    except ValueError as error:
        print(f"PreFine startup error: {error}", file=sys.stderr)
        return 64
    print(f"{identity.uid}:{identity.gid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Replace the entrypoint with mount preparation and privilege drop**

Set `docker/entrypoint.sh` to:

```sh
#!/bin/sh
set -eu

identity="$(python -m backend.app.container_identity)" || exit $?
puid="${identity%%:*}"
pgid="${identity##*:}"

if ! groupmod --non-unique --gid "$pgid" prefine; then
  echo "PreFine startup error: could not set prefine PGID to $pgid" >&2
  exit 70
fi

if ! usermod --non-unique --uid "$puid" --gid "$pgid" prefine; then
  echo "PreFine startup error: could not set prefine PUID to $puid" >&2
  exit 70
fi

if ! mkdir -p /data || ! chown -R "$puid:$pgid" /data; then
  echo "PreFine startup error: cannot prepare /data; check PREFINE_DATA_DIR, PUID=$puid and PGID=$pgid" >&2
  exit 73
fi

exec gosu "$puid:$pgid" sh -c '
  python -m alembic -c backend/alembic.ini upgrade head
  exec python -m uvicorn backend.app.main:create_app \
    --factory \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1
'
```

Update the runtime stage of `Dockerfile` to install `gosu`, create `prefine`, copy `/usr/local/bin/prefine-entrypoint`, and intentionally omit a `USER` instruction because the entrypoint must prepare the bind mount before dropping privileges:

```dockerfile
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    TZ=Asia/Shanghai

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system prefine \
    && useradd --system --gid prefine --home-dir /app --shell /usr/sbin/nologin prefine \
    && mkdir -p /data

COPY pyproject.toml ./
COPY backend/ backend/
RUN python -m pip install --no-cache-dir .

COPY --from=frontend-builder /build/frontend/dist frontend/dist
COPY docker/entrypoint.sh /usr/local/bin/prefine-entrypoint
RUN sed -i 's/\r$//' /usr/local/bin/prefine-entrypoint \
    && chmod 0555 /usr/local/bin/prefine-entrypoint

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"]

ENTRYPOINT ["prefine-entrypoint"]
```

Keep the existing frontend-builder stage unchanged except for any PreFine metadata.

- [ ] **Step 5: Run unit and static shell verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_container_identity.py -v
.\.venv\Scripts\python.exe -m ruff check backend
& 'C:\Users\Thou\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\bin\sh.exe' -n docker/entrypoint.sh
```

Expected: pytest and Ruff pass; shell syntax exits `0` with no output.

- [ ] **Step 6: Commit the container runtime**

Run:

```powershell
git add backend/app/container_identity.py backend/tests/test_container_identity.py docker/entrypoint.sh Dockerfile
git diff --cached --check
git commit -m "feat(container): support bind-mount ownership"
```

### Task 3: Switch Compose and Documentation to Pull-Only Deployment

**Files:**
- Create: `backend/tests/test_container_distribution.py`
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `.gitignore`
- Modify: `.dockerignore`
- Modify: `README.md`
- Modify: `docs/operations.md`

**Interfaces:**
- Consumes: public image tags, PUID/PGID entrypoint, existing application environment variables.
- Produces: a pull-only Compose file, default `./data` bind mount, and README content containing the exact Compose document.

- [ ] **Step 1: Write the failing distribution contract**

Create `backend/tests/test_container_distribution.py`:

```python
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
```

- [ ] **Step 2: Run the contract to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_container_distribution.py -v
```

Expected: FAIL because Compose still contains a local build and named volume.

- [ ] **Step 3: Replace Compose with the exact pull-only document**

Set `docker-compose.yml` to:

```yaml
services:
  app:
    image: ghcr.io/thougyeongcho/prefine:${PREFINE_VERSION:-latest}
    pull_policy: always
    restart: unless-stopped
    ports:
      - "${APP_PORT:-8000}:8000"
    environment:
      PUID: "${PUID:-1000}"
      PGID: "${PGID:-1000}"
      ADMIN_USERNAME: "${ADMIN_USERNAME:?请在 .env 中设置 ADMIN_USERNAME}"
      ADMIN_PASSWORD: "${ADMIN_PASSWORD:?请在 .env 中设置 ADMIN_PASSWORD}"
      SESSION_SECRET: "${SESSION_SECRET:?请在 .env 中设置 SESSION_SECRET}"
      DATA_DIR: /data
      COOKIE_SECURE: "${COOKIE_SECURE:-false}"
      TZ: "${TZ:-Asia/Shanghai}"
      SMTP_HOST: "${SMTP_HOST:-}"
      SMTP_PORT: "${SMTP_PORT:-}"
      SMTP_USERNAME: "${SMTP_USERNAME:-}"
      SMTP_PASSWORD: "${SMTP_PASSWORD:-}"
      SMTP_FROM: "${SMTP_FROM:-}"
      REMINDER_TO_EMAIL: "${REMINDER_TO_EMAIL:-}"
      SMTP_USE_TLS: "${SMTP_USE_TLS:-false}"
      SMTP_STARTTLS: "${SMTP_STARTTLS:-false}"
    volumes:
      - "${PREFINE_DATA_DIR:-./data}:/data"
```

Add these exact lines to `.env.example`:

```dotenv
PREFINE_VERSION=latest
PREFINE_DATA_DIR=./data
PUID=1000
PGID=1000
```

Add `/data/` to `.gitignore` and `/data` to `.dockerignore`.

- [ ] **Step 4: Rewrite deployment documentation**

README must lead with this deployment path and embed the complete Compose file verbatim:

```bash
cp .env.example .env
# 编辑 .env：设置 ADMIN_PASSWORD，并生成至少 32 字符的 SESSION_SECRET
docker compose up -d
```

Document upgrade and version pinning exactly:

```bash
docker compose pull
docker compose up -d

# 固定版本：在 .env 中设置 PREFINE_VERSION=0.1.0
```

Update `docs/operations.md` so backup copies `${PREFINE_DATA_DIR:-./data}/prefine.db`, restore uses the same host directory, and no command uses `--build` or a named volume.

- [ ] **Step 5: Run the distribution contract**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_container_distribution.py -v
```

Expected: 3 tests pass.

- [ ] **Step 6: Commit the pull-only deployment**

Run:

```powershell
git add docker-compose.yml .env.example .gitignore .dockerignore README.md docs/operations.md backend/tests/test_container_distribution.py
git diff --cached --check
git commit -m "feat(container): pull prefine from ghcr"
```

### Task 4: Publish Immutable, Multi-Architecture Images in GitHub Actions

**Files:**
- Create: `.github/workflows/publish-container.yml`
- Extend: `backend/tests/test_container_distribution.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: Dockerfile, public image name, default branch `main`, `vX.Y.Z` Git tags, and `GITHUB_TOKEN`.
- Produces: `latest` on `main`, exact `X.Y.Z` on version tags, amd64/arm64 manifests, OCI metadata, provenance, and SBOM attestations.

- [ ] **Step 1: Add a failing workflow policy test**

Append to `backend/tests/test_container_distribution.py`:

```python
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
    assert "imagetools inspect" in workflow
    assert "@v" not in workflow
```

- [ ] **Step 2: Run the policy test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_container_distribution.py::test_publish_workflow_is_pinned_and_multi_architecture -v
```

Expected: FAIL because the workflow does not exist.

- [ ] **Step 3: Create the pinned publication workflow**

Create `.github/workflows/publish-container.yml`:

```yaml
name: Publish container image

on:
  push:
    branches:
      - main
    tags:
      - "v*.*.*"
  workflow_dispatch:

permissions:
  contents: read
  packages: write

concurrency:
  group: prefine-container-${{ github.ref }}
  cancel-in-progress: false

env:
  IMAGE_NAME: ghcr.io/thougyeongcho/prefine

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - name: Check out repository
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1

      - name: Set up QEMU
        uses: docker/setup-qemu-action@96fe6ef7f33517b61c61be40b68a1882f3264fb8 # v4.2.0

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@bb05f3f5519dd87d3ba754cc423b652a5edd6d2c # v4.2.0

      - name: Log in to GHCR
        uses: docker/login-action@af1e73f918a031802d376d3c8bbc3fe56130a9b0 # v4.4.0
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Generate image metadata
        id: meta
        uses: docker/metadata-action@dc802804100637a589fabce1cb79ff13a1411302 # v6.2.0
        with:
          images: ${{ env.IMAGE_NAME }}
          flavor: latest=false
          tags: |
            type=raw,value=latest,enable=${{ github.ref == 'refs/heads/main' }}
            type=semver,pattern={{version}},enable=${{ startsWith(github.ref, 'refs/tags/v') }}
          labels: |
            org.opencontainers.image.title=PreFine
            org.opencontainers.image.description=Private-by-design finance tools for mainland China teams

      - name: Build and push image
        uses: docker/build-push-action@53b7df96c91f9c12dcc8a07bcb9ccacbed38856a # v7.3.0
        with:
          context: .
          platforms: linux/amd64,linux/arm64
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
          provenance: mode=max
          sbom: true

      - name: Verify multi-architecture manifest
        shell: bash
        env:
          IMAGE_TAGS: ${{ steps.meta.outputs.tags }}
        run: |
          set -euo pipefail
          while IFS= read -r image_tag; do
            [ -n "$image_tag" ] || continue
            manifest="$(docker buildx imagetools inspect "$image_tag")"
            printf '%s\n' "$manifest"
            grep -q 'linux/amd64' <<<"$manifest"
            grep -q 'linux/arm64' <<<"$manifest"
          done <<<"$IMAGE_TAGS"
```

- [ ] **Step 4: Document automatic publication and public pulls**

Add README text stating that users do not build locally, `main` produces `latest`, `v0.1.0` produces only `0.1.0`, both platforms are supported, and the image is anonymously pullable after the package visibility gate.

- [ ] **Step 5: Run workflow contract and project lint**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_container_distribution.py -v
.\.venv\Scripts\python.exe -m ruff check backend
```

Expected: all distribution tests and Ruff pass.

- [ ] **Step 6: Commit the publication workflow**

Run:

```powershell
git add .github/workflows/publish-container.yml backend/tests/test_container_distribution.py README.md
git diff --cached --check
git commit -m "ci(container): publish prefine to ghcr"
```

### Task 5: Run the Fail-Closed Private Security Gate

**Files:**
- Verify: all tracked files and all reachable Git commits
- Verify: `pyproject.toml` dependency graph
- Verify: `frontend/pnpm-lock.yaml` production dependency graph
- Verify: final staged changes and GitHub Actions policy

**Interfaces:**
- Consumes: a still-private repository and a clean local `main` containing Tasks 1–4.
- Produces: evidence that secrets, forbidden files, high/critical production vulnerabilities, legacy identifiers, test failures, and action-policy violations do not remain.

- [ ] **Step 1: Install pinned audit and history tools into the ignored virtual environment**

Run:

```powershell
.\.venv\Scripts\python.exe -m pip install pip-audit==2.10.1 git-filter-repo==2.47.0
```

Expected: both tools install under `.venv`; `git status --short` remains clean.

- [ ] **Step 2: Download and verify Gitleaks 8.30.1 outside the repository**

Download `gitleaks_8.30.1_windows_x64.zip` and `gitleaks_8.30.1_checksums.txt` from the official `gitleaks/gitleaks` GitHub release into a newly created system temporary directory. Verify the archive SHA-256 before extraction. Never add the binary, archive, checksum, or scan output to the project:

```powershell
$toolDirectory = Join-Path ([System.IO.Path]::GetTempPath()) ("prefine-security-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $toolDirectory -ErrorAction Stop | Out-Null
$archiveName = 'gitleaks_8.30.1_windows_x64.zip'
$archivePath = Join-Path $toolDirectory $archiveName
$checksumsPath = Join-Path $toolDirectory 'gitleaks_8.30.1_checksums.txt'
Invoke-WebRequest "https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/$archiveName" -OutFile $archivePath
Invoke-WebRequest 'https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_checksums.txt' -OutFile $checksumsPath
$checksumLine = Get-Content -LiteralPath $checksumsPath | Where-Object { $_ -match ("\s+" + [regex]::Escape($archiveName) + '$') }
if (($checksumLine | Measure-Object).Count -ne 1) { throw 'Gitleaks checksum entry missing or ambiguous' }
$expectedHash = (($checksumLine -split '\s+')[0]).ToUpperInvariant()
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $archivePath).Hash
if ($actualHash -ne $expectedHash) { throw 'Gitleaks archive checksum mismatch' }
Expand-Archive -LiteralPath $archivePath -DestinationPath $toolDirectory
$gitleaksExecutable = Join-Path $toolDirectory 'gitleaks.exe'
& $gitleaksExecutable git . --redact --no-banner
```

Expected: exit code `0`, with no detected secrets in complete reachable history.

- [ ] **Step 3: Audit production dependencies**

Run:

```powershell
.\.venv\Scripts\python.exe -m pip_audit . --strict --progress-spinner off
$env:PATH = 'C:\Users\Thou\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin;' + $env:PATH
& 'C:\Users\Thou\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd' --dir frontend audit --prod --audit-level high
```

Expected: no known Python vulnerability and no high/critical production frontend vulnerability. A registry/audit-service error is a blocker, not a pass.

- [ ] **Step 4: Verify tracked paths, current naming, credentials, and history objects**

Run path and credential-shape scans over the current tree and `git log -p --all`. Verify that `.env`, databases, `.venv`, dependencies, caches, reports, and build output are absent from tracked paths. The six process PNG objects may still appear only in historical objects until Task 6. Verify the confirmed final Logo hash again:

```powershell
$forbiddenTracked = git ls-files | Select-String -Pattern '(^|/)(\.env$|\.venv/|\.pnpm-store/|node_modules/|dist/|playwright-report/|test-results/|__pycache__/|[^/]*\.db(?:-shm|-wal)?$)'
if ($forbiddenTracked) { $forbiddenTracked; throw 'Forbidden tracked paths found' }
$credentialPattern = '(BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|AKIA[0-9A-Z]{16})'
$currentMatches = rg -n --hidden --no-messages --glob '!.git/**' --glob '!.venv/**' --glob '!node_modules/**' --glob '!frontend/node_modules/**' $credentialPattern .
if ($LASTEXITCODE -eq 0) { $currentMatches; throw 'Credential pattern found in current tree' }
if ($LASTEXITCODE -gt 1) { throw 'Current-tree credential scan failed' }
$historyMatches = git log -p --all --no-ext-diff --text | rg -n $credentialPattern
if ($LASTEXITCODE -eq 0) { $historyMatches; throw 'Credential pattern found in Git history' }
if ($LASTEXITCODE -gt 1) { throw 'Git-history credential scan failed' }
Get-FileHash -Algorithm SHA256 -LiteralPath 'assets/branding/prefine-logo-512.png'
```

Use a split marker so the audit command itself does not create a tracked legacy match:

```powershell
$legacySlug = 'finance' + '-' + 'toolkit'
$legacyTitle = 'Finance' + ' ' + 'Toolkit'
rg -ni --hidden --glob '!.git/**' --glob '!.venv/**' --glob '!node_modules/**' --glob '!frontend/node_modules/**' "$legacySlug|$legacyTitle" .
```

Expected: no current-tree matches.

- [ ] **Step 5: Run the complete application verification suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests
.\.venv\Scripts\python.exe -m ruff check backend
$pnpm = 'C:\Users\Thou\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd'
$env:PATH = 'C:\Users\Thou\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin;' + $env:PATH
& $pnpm --dir frontend lint
Push-Location frontend
try { & '.\node_modules\.bin\vitest.cmd' run } finally { Pop-Location }
& $pnpm --dir frontend build
$env:PLAYWRIGHT_CHANNEL = 'msedge'
& $pnpm --dir frontend e2e
```

Expected: 0 failures. Docker is deliberately not built locally.

- [ ] **Step 6: Verify a clean, publishable branch**

Run:

```powershell
git diff --check
git status --short --branch
git log --oneline --decorate -8
```

Expected: worktree clean; local `main` is ahead of the still-private `origin/main` only by reviewed commits.

### Task 6: Rewrite Private History and Push with an Exact Lease

**Files:**
- Rewrite: all reachable Git commits containing the six process PNG paths
- Backup: a Git bundle in a newly created non-project system temporary directory
- Update: private `origin/main`

**Interfaces:**
- Consumes: clean verified local history, authenticated GitHub access, exact remote SHA, and the six approved removal paths.
- Produces: a private remote `main` whose reachable objects contain only the final Logo and which triggers the private `latest` workflow.

- [ ] **Step 1: Freeze the exact remote state and privacy precondition**

Run:

```powershell
$remoteBefore = (git ls-remote origin refs/heads/main).Split("`t")[0]
gh repo view ThouGyeongcho/PreFine --json visibility,defaultBranchRef,url
```

Expected: a 40-character `$remoteBefore`, visibility `PRIVATE`, default branch `main`.

- [ ] **Step 2: Create and verify an off-workspace recovery bundle**

Create a unique directory under `[System.IO.Path]::GetTempPath()`, resolve its absolute path, and run:

```powershell
git bundle create $bundlePath --all
git bundle verify $bundlePath
```

Expected: verification reports a complete bundle. Record the absolute bundle path for final handoff; never copy it into the workspace.

- [ ] **Step 3: Rewrite the six exact paths out of all local history**

Run the six exact paths without a wildcard, then restore `origin` if filter-repo removes it:

```powershell
& '.\.venv\Scripts\git-filter-repo.exe' --invert-paths --force `
  --path 'assets/branding/prefine-logo-option-1-512.png' `
  --path 'assets/branding/prefine-logo-option-2-512.png' `
  --path 'assets/branding/prefine-logo-option-3-512.png' `
  --path 'assets/branding/prefine-logo-option-4-512.png' `
  --path 'assets/branding/prefine-logo-option-5-512.png' `
  --path 'assets/branding/prefine-logo-options-contact-sheet.png'
if (-not (git remote)) {
  git remote add origin 'https://github.com/ThouGyeongcho/PreFine.git'
}
```

- [ ] **Step 4: Verify the rewritten history locally**

Run:

```powershell
git status --short --branch
git rev-list --objects --all
Get-FileHash -Algorithm SHA256 assets/branding/prefine-logo-512.png
```

Expected: clean `main`; none of the six removed paths appears in `git rev-list --objects --all`; final Logo hash is `AC9901D5C3DAC3D3B67B287F2D63C050465066C609AA269EC619200409992DF7`.

- [ ] **Step 5: Force-push only when the lease still matches**

Run:

```powershell
git push --force-with-lease="refs/heads/main:$remoteBefore" origin main
```

Expected: push succeeds. Any stale-info/lease failure stops the task; fetch and review remote changes instead of overriding them.

- [ ] **Step 6: Verify private remote history and SHA**

Compare `git rev-parse HEAD` with GitHub's `main` commit SHA. Query the remote tree/history and confirm the six paths are absent. Re-run Gitleaks against the rewritten reachable history. Do not change repository visibility yet.

### Task 7: Publish the Repository and Two Public Image Tags

**Files:**
- External: GitHub Actions workflow runs
- External: repository visibility
- External: GHCR package visibility
- External: Git tag `v0.1.0`

**Interfaces:**
- Consumes: rewritten private `main`, successful security gate, Actions build permissions, and the approved irreversible public-package decision.
- Produces: public repository, public anonymous GHCR package, and `latest`/`0.1.0` amd64+arm64 manifests.

- [ ] **Step 1: Wait for the private `latest` workflow**

Use `gh run list` to find the run for the rewritten `main`, then:

```powershell
gh run watch $runId --exit-status
```

Expected: workflow conclusion `success`; logs show both platform entries in the manifest verification step.

- [ ] **Step 2: Repeat the remote public-safety gate**

Verify the remote SHA, current tree, reachable object paths, Gitleaks result, dependency-audit results, final Logo hash, workflow permissions, and repository visibility `PRIVATE`. Any difference from Task 5/6 stops publication.

- [ ] **Step 3: Make the source repository public**

Run only after Step 2 passes:

```powershell
gh repo edit ThouGyeongcho/PreFine --visibility public --accept-visibility-change-consequences
```

Expected: unauthenticated `GET https://api.github.com/repos/ThouGyeongcho/PreFine` returns `private: false` and `default_branch: main`.

- [ ] **Step 4: Make the GHCR package public**

Open the authenticated package settings page for `ThouGyeongcho/prefine`, choose **Change visibility → Public**, and confirm the irreversible change. If no authenticated browser session is available, stop and ask the user to perform this single UI confirmation; do not claim the package is public.

- [ ] **Step 5: Verify anonymous `latest` access and platforms**

Without GitHub authentication, request a pull token from `https://ghcr.io/token?service=ghcr.io&scope=repository:thougyeongcho/prefine:pull`, then fetch the `latest` OCI index from `https://ghcr.io/v2/thougyeongcho/prefine/manifests/latest`. Verify HTTP success and architectures `amd64` and `arm64`.

- [ ] **Step 6: Create the immutable first version tag**

Verify no local or remote `v0.1.0` exists and the working tree is clean, then run:

```powershell
git tag -a v0.1.0 -m "PreFine 0.1.0"
git push origin v0.1.0
```

Expected: the tag points to the same commit already published as `latest`; no force or tag movement occurs.

- [ ] **Step 7: Wait for and verify `0.1.0`**

Watch the tag-triggered workflow with `gh run watch --exit-status`. Repeat the unauthenticated GHCR token/manifest check for `0.1.0`, verify amd64 and arm64, and verify no `0.1` or `0` tags were generated.

- [ ] **Step 8: Final repository verification**

Run:

```powershell
git status --short --branch
git remote -v
git rev-parse HEAD
git rev-list --objects --all
gh repo view ThouGyeongcho/PreFine --json nameWithOwner,visibility,defaultBranchRef,url
```

Expected: clean `main` tracking `origin/main`; repository `PUBLIC`; remote SHA matches local; only the final Logo is reachable; public `latest` and `0.1.0` manifests contain both requested platforms. Report the off-workspace recovery bundle path and that Docker was not built locally.
