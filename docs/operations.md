# PreFine operations guide

## Deploy and upgrade

PreFine deployments pull published images; do not build Docker images on the
deployment host. Copy `.env.example` to `.env`, replace every `CHANGE_ME` value,
and use a random `SESSION_SECRET` of at least 32 characters.

```sh
docker compose pull
docker compose up -d
curl --fail http://localhost:8000/api/health
```

`latest` follows `main`. To pin a version, set `PREFINE_VERSION` in `.env` to a
published release version such as `0.1.0`. Only canonical semantic-version tags
create GitHub Releases.

For a single-layer reverse proxy, list its exact direct IP in
`TRUSTED_PROXY_IPS`. The proxy must overwrite `X-Forwarded-For` with one client
IP. Leave this setting empty unless that condition is true; it is the secure
default. Set `COOKIE_SECURE=true` when serving PreFine behind an HTTPS reverse
proxy.

## Backup and restore

Backups are stored inside `${PREFINE_DATA_DIR}/backups`. Run maintenance only
through the application maintenance commands. A failed backup or restore
intentionally leaves the app stopped. Restore automatically creates a validated
`pre-restore-*` backup before changing the database.

### POSIX sh backup

```sh
set -eu
docker compose stop app
running_services="$(docker compose ps --status running --services)"
if printf '%s\n' "$running_services" | grep -qx app; then
  echo "PreFine app is still running; maintenance aborted" >&2
  exit 1
fi
docker compose run --rm --no-deps app \
  python -m backend.app.database_maintenance backup
docker compose start app
curl --fail http://localhost:8000/api/health
```

### POSIX sh restore

```sh
set -eu
docker compose stop app
running_services="$(docker compose ps --status running --services)"
if printf '%s\n' "$running_services" | grep -qx app; then
  echo "PreFine app is still running; maintenance aborted" >&2
  exit 1
fi
docker compose run --rm --no-deps app \
  python -m backend.app.database_maintenance restore prefine-20260722T120000Z.db
docker compose start app
curl --fail http://localhost:8000/api/health
```

### PowerShell backup

```powershell
$ErrorActionPreference = "Stop"

docker compose stop app
if ($LASTEXITCODE -ne 0) { throw "docker compose stop failed" }
$runningServices = docker compose ps --status running --services
if ($LASTEXITCODE -ne 0) { throw "docker compose ps failed" }
if ($runningServices -contains "app") {
  throw "PreFine app is still running; maintenance aborted"
}
docker compose run --rm --no-deps app python -m backend.app.database_maintenance backup
if ($LASTEXITCODE -ne 0) { throw "PreFine backup failed; app remains stopped" }
docker compose start app
if ($LASTEXITCODE -ne 0) { throw "docker compose start failed" }
Invoke-RestMethod http://localhost:8000/api/health
```

### PowerShell restore

```powershell
$ErrorActionPreference = "Stop"

docker compose stop app
if ($LASTEXITCODE -ne 0) { throw "docker compose stop failed" }
$runningServices = docker compose ps --status running --services
if ($LASTEXITCODE -ne 0) { throw "docker compose ps failed" }
if ($runningServices -contains "app") {
  throw "PreFine app is still running; maintenance aborted"
}
docker compose run --rm --no-deps app python -m backend.app.database_maintenance restore prefine-20260722T120000Z.db
if ($LASTEXITCODE -ne 0) { throw "PreFine restore failed; app remains stopped" }
docker compose start app
if ($LASTEXITCODE -ne 0) { throw "docker compose start failed" }
Invoke-RestMethod http://localhost:8000/api/health
```
