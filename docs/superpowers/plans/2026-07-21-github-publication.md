# PreFine GitHub Publication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the complete PreFine V1 to a new private `ThouGyeongcho/PreFine` repository with reproducible Docker instructions and the complete Compose file in README.

**Architecture:** Keep the runnable Compose configuration authoritative at the repository root and mirror it verbatim in README. Protect local-only state through `.gitignore`, then publish the reviewed initial history directly to `main` because the remote repository has no pre-existing base branch.

**Tech Stack:** Git, GitHub CLI, Docker Compose, Markdown, PowerShell

## Global Constraints

- The GitHub repository must be private and named `ThouGyeongcho/PreFine`.
- The default and published branch must be `main`.
- Do not commit `.superpowers/`, `.pnpm-store/`, `.env`, credentials, SQLite databases, dependency directories, caches, test output, or build output.
- README must contain copyable Docker lifecycle commands and the complete root `docker-compose.yml` verbatim.
- `ADMIN_PASSWORD` must be replaced before startup and `SESSION_SECRET` must contain at least 32 characters; SMTP remains optional.
- Preserve the single Uvicorn worker, non-root container user, Alembic startup migration, and `prefine-data` named volume.
- If `ThouGyeongcho/PreFine` already exists, inspect it and stop instead of overwriting unknown history.

---

### Task 1: Protect Local-Only Files

**Files:**
- Modify: `.gitignore`

**Interfaces:**
- Consumes: repository-local cache directories currently present in the working tree.
- Produces: Git ignore rules that make `git status --short` exclude `.superpowers/` and `.pnpm-store/`.

- [x] **Step 1: Verify the current ignore rules fail**

Run:

```powershell
git check-ignore .superpowers .pnpm-store
```

Expected: exit code `1` because neither path is ignored yet.

- [x] **Step 2: Add the exact ignore rules**

Append to `.gitignore`:

```gitignore
.superpowers/
.pnpm-store/
```

- [x] **Step 3: Verify both paths are ignored**

Run:

```powershell
git check-ignore -v .superpowers .pnpm-store
```

Expected: two lines identifying the new `.gitignore` rules.

### Task 2: Document the Complete Docker Workflow

**Files:**
- Modify: `README.md`
- Read: `docker-compose.yml`
- Read: `.env.example`

**Interfaces:**
- Consumes: environment-variable names and the authoritative root Compose configuration.
- Produces: Docker setup, health, logs, restart, stop, rebuild, and volume-removal instructions plus a byte-for-byte Compose YAML block.

- [x] **Step 1: Verify README does not yet contain the complete Compose document**

Run:

```powershell
$readme = Get-Content -Raw -Encoding UTF8 README.md
$compose = (Get-Content -Raw -Encoding UTF8 docker-compose.yml).TrimEnd()
if ($readme.Contains("```yaml`n$compose`n```")) { exit 0 } else { exit 1 }
```

Expected: exit code `1` before the README update.

- [x] **Step 2: Expand the Docker deployment section**

Document these commands, keeping the existing product, development, verification, and project-structure sections:

```bash
cp .env.example .env
docker compose up --build -d
docker compose ps
curl http://localhost:8000/api/health
docker compose logs -f --tail=200 app
docker compose restart app
docker compose down
docker compose up --build -d
```

Also include the PowerShell equivalent `Copy-Item .env.example .env`, warn that `docker compose down -v` permanently removes the application data volume, and embed the exact contents of `docker-compose.yml` in a fenced `yaml` block.

- [x] **Step 3: Verify README and Compose remain synchronized**

Run:

```powershell
$readme = (Get-Content -Raw -Encoding UTF8 README.md) -replace "`r`n", "`n"
$compose = ((Get-Content -Raw -Encoding UTF8 docker-compose.yml) -replace "`r`n", "`n").TrimEnd()
if (-not $readme.Contains("```yaml`n$compose`n```")) { throw 'README Compose block differs from docker-compose.yml' }
```

Expected: exit code `0` with no output.

### Task 3: Verify and Publish V1

**Files:**
- Stage: all non-ignored repository files
- Verify: `.gitignore`, `.env.example`, `README.md`, `docker-compose.yml`, source, tests, migrations, and operational documentation

**Interfaces:**
- Consumes: the reviewed local `main` branch and authenticated GitHub CLI account `ThouGyeongcho`.
- Produces: private GitHub repository `ThouGyeongcho/PreFine` whose remote `main` tip matches the local release commit.

- [x] **Step 1: Check for secrets and unintended generated files**

Run:

```powershell
git status --short --ignored
rg -n --hidden --glob '!.git/**' --glob '!.superpowers/**' --glob '!.pnpm-store/**' '(BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})'
```

Expected: `.superpowers/`, `.pnpm-store/`, `.env`, dependencies, caches, databases, test output, and build output are absent or ignored; the credential scan has no matches.

- [x] **Step 2: Run release verification**

Run:

```powershell
python -m pytest backend/tests
ruff check backend
pnpm --dir frontend lint
pnpm --dir frontend exec vitest run
pnpm --dir frontend build
pnpm --dir frontend e2e
```

Expected: every command exits `0`. If Docker is installed, also run `docker compose config --quiet`; otherwise record the missing Docker runtime as an explicit validation gap.

- [ ] **Step 3: Create the V1 release commit**

Run:

```powershell
git add -A
git diff --cached --check
git diff --cached --name-status
git commit -m "feat: release prefine v1"
```

Expected: one Conventional Commit containing the complete V1 and no ignored local-only files.

- [ ] **Step 4: Confirm the target is unused, then create and push it**

Run:

```powershell
gh repo view ThouGyeongcho/PreFine
gh repo create ThouGyeongcho/PreFine --private --source . --remote origin
git push -u origin main
```

Expected: `gh repo view` initially reports that the repository does not exist; creation succeeds; `main` is pushed and tracks `origin/main`.

- [ ] **Step 5: Verify local and remote publication state**

Run:

```powershell
git status --short --branch
git remote -v
git rev-parse HEAD
gh repo view ThouGyeongcho/PreFine --json nameWithOwner,visibility,defaultBranchRef,url
gh api repos/ThouGyeongcho/PreFine/commits/main --jq .sha
```

Expected: the worktree is clean, `origin` targets `ThouGyeongcho/PreFine`, visibility is `PRIVATE`, the default branch is `main`, and the local and remote SHA values are identical.
