# PreFine Publication Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在公开 PreFine 前修复最终安全审查问题，并让正式 GitHub Release 只在对应双架构 GHCR 镜像验证成功后同步发布。

**Architecture:** 后端以 Pydantic 配置验证、失败关闭的同源检查和显式单层代理信任边界保护认证；数据库维护由镜像内的独立 Python CLI 完成一致快照、完整性检查和原子替换；前端通过统一会话失效事件清理 React Query 数据。GitHub Actions 依次执行源码门禁、单架构运行烟测、多架构推送、manifest 验证和版本 Release 创建，任何失败都会阻止后续公开动作。

**Tech Stack:** Python 3.12、FastAPI、Pydantic v2、SQLite、pytest、React 19、TypeScript、TanStack Query 5、Vitest、Playwright、Docker Buildx、GitHub Actions、GHCR、GitHub CLI。

## Global Constraints

- 产品文案使用 `PreFine`，技术标识使用 `prefine`，镜像固定为 `ghcr.io/thougyeongcho/prefine`。
- 金额计算继续只使用 `Decimal`；不得改写官方 `bssz`，未知税务项目继续显示“其他待确认”。
- 本地流程不得构建 Docker 镜像；GitHub Actions 是唯一镜像构建者。
- 容器只以 root 准备 `/data`，迁移、维护命令和 Web 服务必须以指定 PUID/PGID 的非 root 用户运行。
- Compose 保持 pull-only，并固定挂载 `${PREFINE_DATA_DIR:-./data}:/data`。
- 正式镜像只发布 `latest` 和精确 `X.Y.Z`；不得生成 `X.Y` 或 `X`。
- 目标平台固定为 `linux/amd64` 和 `linux/arm64`。
- 仓库、GHCR 包和 `v0.1.0` 在全部私有验证通过前不得公开或创建。
- MIT 版权行固定为 `Copyright (c) 2026 ThouGyeongcho`。
- 每个行为变更必须先写失败测试，最小实现后运行针对性测试和关联回归测试。

---

## File Structure

- `backend/app/config.py`: 凭据和受信代理环境变量的唯一验证入口。
- `backend/app/auth.py`: 会话同源验证和登录限流客户端地址解析。
- `backend/app/database_maintenance.py`: 备份、恢复、完整性检查和 CLI 退出码。
- `backend/app/tax_source.py`: 12366 请求标识。
- `docker/entrypoint.sh`: 默认服务路径和显式维护命令路径的降权分派。
- `docker/smoke-test.sh`: 仅供 GitHub Actions 调用的真实镜像运行烟测。
- `frontend/src/api/session.ts`: 与 React 无关的 401 会话失效事件。
- `frontend/src/components/SessionBoundary.tsx`: React Query 清理和登录替换导航。
- `frontend/src/components/TaxToolSettings.tsx`: 提醒天数文本草稿和服务器结果同步。
- `.github/workflows/publish-container.yml`: 分阶段安全门禁、镜像发布和 GitHub Release 同步。
- `LICENSE`, `SECURITY.md`, `README.md`, `docs/operations.md`, `.env.example`, `AGENTS.md`: 公开许可、安全报告和部署运维契约。

---

### Task 1: Fail-Closed Backend Authentication Boundary

**Files:**
- Create: `backend/tests/test_config.py`
- Create: `backend/tests/http_helpers.py`
- Modify: `backend/app/config.py`
- Modify: `backend/app/auth.py`
- Modify: `backend/app/tax_source.py`
- Modify: `docker/entrypoint.sh`
- Modify: `docker-compose.yml`
- Modify: `README.md` (仅同步其中的完整 Compose 代码块)
- Modify: `backend/tests/test_auth.py`
- Modify: `backend/tests/test_money_api.py`
- Modify: `backend/tests/test_calendar_api.py`
- Modify: `backend/tests/test_tax_settings_api.py`
- Modify: `backend/tests/test_test_email_api.py`
- Modify: `backend/tests/test_tax_source.py`
- Modify: `backend/tests/test_prefine_identity.py`

**Interfaces:**
- Consumes: existing `Settings`, `AuthService`, `require_same_origin(request)`, and `client_ip(request)` APIs.
- Produces: `Settings.trusted_proxy_addresses: frozenset[IPv4Address | IPv6Address]`; fail-closed `require_same_origin`; proxy-aware `client_ip`; `SAME_ORIGIN_HEADERS` for authenticated write tests.

- [ ] **Step 1: Add failing settings tests**

Create `backend/tests/test_config.py` with exact validation cases:

```python
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.config import Settings


def valid_values(tmp_path: Path) -> dict[str, object]:
    return {
        "ADMIN_USERNAME": "admin",
        "ADMIN_PASSWORD": "correct horse battery staple",
        "SESSION_SECRET": "0123456789abcdef0123456789abcdef",
        "DATA_DIR": tmp_path,
    }


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("ADMIN_PASSWORD", "short"),
        ("ADMIN_PASSWORD", "CHANGE_ME_ADMIN_PASSWORD"),
        ("SESSION_SECRET", "too-short"),
        ("SESSION_SECRET", "CHANGE_ME_SESSION_SECRET"),
    ],
)
def test_rejects_unsafe_required_credentials(
    tmp_path: Path, name: str, value: str
) -> None:
    values = valid_values(tmp_path)
    values[name] = value
    with pytest.raises(ValidationError) as caught:
        Settings(**values)
    assert name in str(caught.value)
    assert value not in str(caught.value)


def test_normalizes_exact_trusted_proxy_addresses(tmp_path: Path) -> None:
    settings = Settings(
        **valid_values(tmp_path),
        TRUSTED_PROXY_IPS=" 127.0.0.1,2001:db8::1 ",
    )
    assert {str(value) for value in settings.trusted_proxy_addresses} == {
        "127.0.0.1",
        "2001:db8::1",
    }


@pytest.mark.parametrize("value", ["proxy.local", "127.0.0.1,", "127.0.0.1,not-ip"])
def test_rejects_invalid_trusted_proxy_configuration(
    tmp_path: Path, value: str
) -> None:
    with pytest.raises(ValidationError):
        Settings(**valid_values(tmp_path), TRUSTED_PROXY_IPS=value)
```

- [ ] **Step 2: Add failing origin and proxy topology tests**

Add to `backend/tests/test_auth.py`:

```python
def test_authenticated_write_without_source_headers_is_rejected(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        assert client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "correct horse battery staple"},
        ).status_code == 204
        response = client.post("/api/auth/logout")
    assert response.status_code == 403
    assert response.json()["code"] == "origin_not_allowed"


def test_same_origin_fetch_metadata_allows_authenticated_write(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "correct horse battery staple"},
        )
        response = client.post(
            "/api/auth/logout", headers={"Sec-Fetch-Site": "same-origin"}
        )
    assert response.status_code == 204


def test_untrusted_peer_cannot_spoof_forwarded_login_bucket(tmp_path: Path) -> None:
    with make_client(tmp_path, client_address="203.0.113.10") as client:
        for number in range(5):
            response = client.post(
                "/api/auth/login",
                headers={"X-Forwarded-For": f"198.51.100.{number + 1}"},
                json={"username": "admin", "password": "wrong"},
            )
            assert response.status_code == 401
        blocked = client.post(
            "/api/auth/login",
            headers={"X-Forwarded-For": "198.51.100.99"},
            json={"username": "admin", "password": "wrong"},
        )
    assert blocked.status_code == 429


def test_trusted_single_proxy_uses_one_valid_forwarded_address(tmp_path: Path) -> None:
    with make_client(
        tmp_path,
        client_address="192.0.2.10",
        trusted_proxy_ips="192.0.2.10",
    ) as client:
        for number in range(5):
            assert client.post(
                "/api/auth/login",
                headers={"X-Forwarded-For": f"198.51.100.{number + 1}"},
                json={"username": "admin", "password": "wrong"},
            ).status_code == 401


def test_trusted_proxy_rejects_forwarded_chains(tmp_path: Path) -> None:
    with make_client(
        tmp_path,
        client_address="192.0.2.10",
        trusted_proxy_ips="192.0.2.10",
    ) as client:
        for number in range(5):
            assert client.post(
                "/api/auth/login",
                headers={"X-Forwarded-For": f"198.51.100.{number + 1}, 192.0.2.9"},
                json={"username": "admin", "password": "wrong"},
            ).status_code == 401
        blocked = client.post(
            "/api/auth/login",
            headers={"X-Forwarded-For": "198.51.100.99, 192.0.2.9"},
            json={"username": "admin", "password": "wrong"},
        )
    assert blocked.status_code == 429
```

Extend the local helpers exactly as follows, preserving the existing `auth_now` and `cookie_secure` arguments:

```python
def make_settings(
    data_dir: Path,
    *,
    cookie_secure: bool = False,
    trusted_proxy_ips: str = "",
) -> Settings:
    return Settings(
        ADMIN_USERNAME="admin",
        ADMIN_PASSWORD="correct horse battery staple",
        SESSION_SECRET="0123456789abcdef0123456789abcdef",
        DATA_DIR=data_dir,
        COOKIE_SECURE=cookie_secure,
        TRUSTED_PROXY_IPS=trusted_proxy_ips,
    )


def make_client(
    data_dir: Path,
    *,
    auth_now: Callable[[], datetime] | None = None,
    cookie_secure: bool = False,
    trusted_proxy_ips: str = "",
    client_address: str = "testclient",
) -> TestClient:
    app = create_app(
        make_settings(
            data_dir,
            cookie_secure=cookie_secure,
            trusted_proxy_ips=trusted_proxy_ips,
        ),
        start_scheduler=False,
        auth_now=auth_now,
    )
    return TestClient(app, client=(client_address, 50000))
```

- [ ] **Step 3: Run the new backend tests and verify RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_config.py backend/tests/test_auth.py -q
```

Expected: failures for the accepted placeholder password, missing-source logout returning 204, missing `trusted_proxy_addresses`, and forwarded addresses being ignored in all cases.

- [ ] **Step 4: Implement credential and proxy configuration validation**

In `backend/app/config.py`, add `ip_address`, `IPv4Address`, `IPv6Address`, `field_validator`, constants, the field, and property:

```python
from ipaddress import IPv4Address, IPv6Address, ip_address

from pydantic import Field, SecretStr, field_validator, model_validator

EXAMPLE_ADMIN_PASSWORD = "CHANGE_ME_ADMIN_PASSWORD"
EXAMPLE_SESSION_SECRET = "CHANGE_ME_SESSION_SECRET"

admin_password: SecretStr = Field(alias="ADMIN_PASSWORD", min_length=12)
session_secret: SecretStr = Field(alias="SESSION_SECRET", min_length=32)
trusted_proxy_ips: str = Field(default="", alias="TRUSTED_PROXY_IPS")

@field_validator("admin_password")
@classmethod
def reject_example_admin_password(cls, value: SecretStr) -> SecretStr:
    if value.get_secret_value() == EXAMPLE_ADMIN_PASSWORD:
        raise ValueError("ADMIN_PASSWORD 必须替换示例占位值")
    return value

@field_validator("session_secret")
@classmethod
def reject_example_session_secret(cls, value: SecretStr) -> SecretStr:
    if value.get_secret_value() == EXAMPLE_SESSION_SECRET:
        raise ValueError("SESSION_SECRET 必须替换示例占位值")
    return value

@field_validator("trusted_proxy_ips")
@classmethod
def normalize_trusted_proxy_ips(cls, value: str) -> str:
    if value == "":
        return value
    parts = [part.strip() for part in value.split(",")]
    if any(part == "" for part in parts):
        raise ValueError("TRUSTED_PROXY_IPS 只能包含逗号分隔的 IP 地址")
    try:
        return ",".join(str(ip_address(part)) for part in parts)
    except ValueError as error:
        raise ValueError("TRUSTED_PROXY_IPS 只能包含逗号分隔的 IP 地址") from error

@property
def trusted_proxy_addresses(self) -> frozenset[IPv4Address | IPv6Address]:
    if not self.trusted_proxy_ips:
        return frozenset()
    return frozenset(ip_address(part) for part in self.trusted_proxy_ips.split(","))
```

Keep validators inside `Settings`; do not include secret values in messages.

- [ ] **Step 5: Implement fail-closed origin and exact proxy parsing**

Replace the missing-source branch and `client_ip` in `backend/app/auth.py`:

```python
from ipaddress import ip_address


def require_same_origin(request: Request) -> None:
    source = request.headers.get("origin") or request.headers.get("referer")
    request_host = request.headers.get("host", "").lower()
    if source is None:
        if request.headers.get("sec-fetch-site") == "same-origin":
            return
        raise _origin_not_allowed()

    parsed = urlsplit(source)
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != request_host:
        raise _origin_not_allowed()


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client is not None else "unknown"
    try:
        peer_address = ip_address(peer)
    except ValueError:
        return peer

    settings = get_auth_service(request).settings
    if peer_address not in settings.trusted_proxy_addresses:
        return str(peer_address)

    forwarded = request.headers.get("x-forwarded-for", "").strip()
    if not forwarded or "," in forwarded:
        return str(peer_address)
    try:
        return str(ip_address(forwarded))
    except ValueError:
        return str(peer_address)
```

Add `--no-proxy-headers` to the Uvicorn command in `docker/entrypoint.sh`, and add this environment mapping to `docker-compose.yml`:

```yaml
      TRUSTED_PROXY_IPS: "${TRUSTED_PROXY_IPS:-}"
```

Immediately copy the resulting complete `docker-compose.yml` document into the
README Compose code block so the existing byte-for-byte distribution contract
stays green throughout the task sequence. Broader README guidance remains in
Task 5.

- [ ] **Step 6: Make all authenticated write tests explicit about same origin**

Create `backend/tests/http_helpers.py`:

```python
SAME_ORIGIN_HEADERS = {"Origin": "http://testserver"}
```

Import and pass `headers=SAME_ORIGIN_HEADERS` to successful authenticated logout, money conversion, calendar sync, tax settings update, and test-email POST/PUT requests in the listed API tests. Keep the dedicated missing-header and foreign-origin tests unchanged so the rejection paths remain covered.

- [ ] **Step 7: Fix the remaining identity leak and regression coverage**

Change the request header in `backend/app/tax_source.py` to:

```python
"User-Agent": "PreFine/0.1 (+https://github.com/ThouGyeongcho/PreFine)",
```

In `backend/tests/test_tax_source.py`, capture the request and assert:

```python
assert observed_request.headers["User-Agent"] == (
    "PreFine/0.1 (+https://github.com/ThouGyeongcho/PreFine)"
)
```

In `backend/tests/test_prefine_identity.py`, add `condensed_legacy_title = "Finance" + "Toolkit"` and include it in the finding condition.

- [ ] **Step 8: Run Task 1 verification and commit**

Run:

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_config.py backend/tests/test_auth.py backend/tests/test_money_api.py backend/tests/test_calendar_api.py backend/tests/test_tax_settings_api.py backend/tests/test_test_email_api.py backend/tests/test_tax_source.py backend/tests/test_prefine_identity.py backend/tests/test_container_distribution.py -q
.venv\Scripts\python.exe -m ruff check backend
```

Expected: all selected tests pass and Ruff exits 0.

Commit:

```powershell
git add backend/app/config.py backend/app/auth.py backend/app/tax_source.py docker/entrypoint.sh docker-compose.yml README.md backend/tests
git commit -m "fix(security): harden authentication boundaries"
```

---

### Task 2: Atomic Database Maintenance CLI

**Files:**
- Create: `backend/app/database_maintenance.py`
- Create: `backend/tests/test_database_maintenance.py`
- Modify: `docker/entrypoint.sh`
- Modify: `backend/tests/test_container_distribution.py`

**Interfaces:**
- Consumes: `DATA_DIR` through `Settings.database_path` and the existing PUID/PGID entrypoint preparation.
- Produces: `backup_database(data_dir: Path, prefix: str = "prefine") -> Path`, `restore_database(data_dir: Path, backup_name: str) -> Path`, and CLI subcommands `backup` / `restore NAME`.

- [ ] **Step 1: Write failing maintenance tests**

Create `backend/tests/test_database_maintenance.py` with helpers that create a SQLite database and these exact behaviors:

```python
import sqlite3
from pathlib import Path

import pytest

from backend.app.database_maintenance import (
    MaintenanceError,
    backup_database,
    restore_database,
)


def write_value(path: Path, value: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS sample (value TEXT NOT NULL)")
        connection.execute("DELETE FROM sample")
        connection.execute("INSERT INTO sample (value) VALUES (?)", (value,))


def read_value(path: Path) -> str:
    with sqlite3.connect(path) as connection:
        return str(connection.execute("SELECT value FROM sample").fetchone()[0])


def test_backup_creates_a_valid_timestamped_snapshot(tmp_path: Path) -> None:
    write_value(tmp_path / "prefine.db", "before")
    backup = backup_database(tmp_path)
    assert backup.parent == tmp_path / "backups"
    assert backup.name.startswith("prefine-") and backup.suffix == ".db"
    assert read_value(backup) == "before"
    assert not list(tmp_path.rglob("*.tmp"))


def test_restore_preserves_pre_restore_copy_and_replaces_atomically(tmp_path: Path) -> None:
    write_value(tmp_path / "prefine.db", "old-live")
    source = backup_database(tmp_path)
    write_value(source, "restored")
    write_value(tmp_path / "prefine.db", "new-live")
    safety = restore_database(tmp_path, source.name)
    assert read_value(tmp_path / "prefine.db") == "restored"
    assert safety.name.startswith("pre-restore-")
    assert read_value(safety) == "new-live"


@pytest.mark.parametrize("name", ["../prefine.db", "/tmp/prefine.db", "missing.db"])
def test_restore_rejects_escape_and_missing_sources(tmp_path: Path, name: str) -> None:
    write_value(tmp_path / "prefine.db", "live")
    with pytest.raises(MaintenanceError):
        restore_database(tmp_path, name)
    assert read_value(tmp_path / "prefine.db") == "live"


def test_corrupt_backup_never_replaces_live_database(tmp_path: Path) -> None:
    write_value(tmp_path / "prefine.db", "live")
    backups = tmp_path / "backups"
    backups.mkdir()
    (backups / "corrupt.db").write_bytes(b"not sqlite")
    with pytest.raises(MaintenanceError):
        restore_database(tmp_path, "corrupt.db")
    assert read_value(tmp_path / "prefine.db") == "live"
    assert not list(tmp_path.rglob("*.tmp"))
```

Import the module as `maintenance` and add these forced-failure tests:

```python
import backend.app.database_maintenance as maintenance


def test_copy_failure_removes_temporary_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_value(tmp_path / "prefine.db", "live")

    def deny_copy(_: Path, __: Path) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr(maintenance, "_copy_database", deny_copy)
    with pytest.raises(MaintenanceError):
        backup_database(tmp_path)
    assert read_value(tmp_path / "prefine.db") == "live"
    assert not list(tmp_path.rglob("*.tmp"))


def test_restore_replace_failure_keeps_live_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_value(tmp_path / "prefine.db", "backup-value")
    source = backup_database(tmp_path)
    write_value(tmp_path / "prefine.db", "live-value")
    real_replace = maintenance.os.replace
    calls = 0

    def fail_final_replace(source_path: Path, destination_path: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("replace denied")
        real_replace(source_path, destination_path)

    monkeypatch.setattr(maintenance.os, "replace", fail_final_replace)
    with pytest.raises(MaintenanceError):
        restore_database(tmp_path, source.name)
    assert read_value(tmp_path / "prefine.db") == "live-value"
    assert list((tmp_path / "backups").glob("pre-restore-*.db"))
    assert not list(tmp_path.rglob("*.tmp"))
```

- [ ] **Step 2: Run the maintenance test and verify RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_database_maintenance.py -q
```

Expected: collection fails because `backend.app.database_maintenance` does not exist.

- [ ] **Step 3: Implement the focused maintenance module**

Create `backend/app/database_maintenance.py` with these complete boundaries:

```python
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from backend.app.config import get_settings


class MaintenanceError(RuntimeError):
    pass


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _temporary_path(directory: Path, prefix: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        prefix=prefix, suffix=".tmp", dir=directory, delete=False
    )
    handle.close()
    return Path(handle.name)


def _read_only_uri(path: Path) -> str:
    return f"{path.resolve().as_uri()}?mode=ro"


def _integrity_check(path: Path) -> None:
    try:
        with sqlite3.connect(_read_only_uri(path), uri=True) as connection:
            rows = connection.execute("PRAGMA integrity_check").fetchall()
    except sqlite3.Error as error:
        raise MaintenanceError(f"SQLite integrity check failed for {path.name}") from error
    if rows != [("ok",)]:
        raise MaintenanceError(f"SQLite integrity check failed for {path.name}")


def _copy_database(source: Path, destination: Path) -> None:
    try:
        with sqlite3.connect(_read_only_uri(source), uri=True) as source_db:
            with sqlite3.connect(destination) as destination_db:
                source_db.backup(destination_db)
    except (OSError, sqlite3.Error) as error:
        raise MaintenanceError(f"Could not copy SQLite database {source.name}") from error


def _final_path(directory: Path, prefix: str) -> Path:
    path = directory / f"{prefix}-{_timestamp()}.db"
    if path.exists():
        raise MaintenanceError(f"Backup already exists: {path.name}")
    return path


def backup_database(data_dir: Path, prefix: str = "prefine") -> Path:
    source = data_dir / "prefine.db"
    if not source.is_file() or source.is_symlink():
        raise MaintenanceError("Live database /data/prefine.db is missing")
    backup_dir = data_dir / "backups"
    temporary = _temporary_path(backup_dir, f".{prefix}-")
    try:
        _copy_database(source, temporary)
        _integrity_check(temporary)
        final = _final_path(backup_dir, prefix)
        os.replace(temporary, final)
        return final
    except (MaintenanceError, OSError) as error:
        temporary.unlink(missing_ok=True)
        if isinstance(error, MaintenanceError):
            raise
        raise MaintenanceError("Could not finalize SQLite backup") from error


def _resolve_backup(data_dir: Path, backup_name: str) -> Path:
    if Path(backup_name).name != backup_name:
        raise MaintenanceError("Restore source must be a backup file name")
    backup_dir = (data_dir / "backups").resolve()
    candidate = backup_dir / backup_name
    if candidate.is_symlink() or not candidate.is_file():
        raise MaintenanceError(f"Backup does not exist: {backup_name}")
    resolved = candidate.resolve()
    if resolved.parent != backup_dir:
        raise MaintenanceError("Restore source escaped /data/backups")
    return resolved


def restore_database(data_dir: Path, backup_name: str) -> Path:
    source = _resolve_backup(data_dir, backup_name)
    _integrity_check(source)
    safety = backup_database(data_dir, prefix="pre-restore")
    live = data_dir / "prefine.db"
    temporary = _temporary_path(data_dir, ".prefine-restore-")
    try:
        _copy_database(source, temporary)
        _integrity_check(temporary)
        os.replace(temporary, live)
        return safety
    except (MaintenanceError, OSError) as error:
        temporary.unlink(missing_ok=True)
        if isinstance(error, MaintenanceError):
            raise
        raise MaintenanceError("Could not replace live SQLite database") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="prefine-database")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("backup")
    restore = subparsers.add_parser("restore")
    restore.add_argument("backup_name")
    args = parser.parse_args(argv)
    data_dir = get_settings().data_dir
    try:
        if args.command == "backup":
            result = backup_database(data_dir)
            print(result)
        else:
            result = restore_database(data_dir, args.backup_name)
            print(f"pre-restore backup: {result}")
    except MaintenanceError as error:
        print(f"PreFine database maintenance error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Add the non-root maintenance entrypoint path**

In `docker/entrypoint.sh`, immediately after `/data` preparation and before the default migration block, add:

```sh
if [ "$#" -gt 0 ]; then
  exec gosu "$puid:$pgid" "$@"
fi
```

Add contract assertions in `backend/tests/test_container_distribution.py` that this branch occurs after `chown` and before `python -m alembic`, and that it contains `exec gosu "$puid:$pgid" "$@"`.

- [ ] **Step 5: Run Task 2 verification and commit**

Run:

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_database_maintenance.py backend/tests/test_container_distribution.py backend/tests/test_container_identity.py -q
.venv\Scripts\python.exe -m ruff check backend
```

Expected: all selected tests pass; corrupt and forced-failure tests prove the live DB remains unchanged.

Commit:

```powershell
git add backend/app/database_maintenance.py backend/tests/test_database_maintenance.py docker/entrypoint.sh backend/tests/test_container_distribution.py
git commit -m "feat(database): add atomic maintenance commands"
```

---

### Task 3: Frontend Session Isolation and Reminder Drafts

**Files:**
- Create: `frontend/src/api/session.ts`
- Create: `frontend/src/api/client.test.ts`
- Create: `frontend/src/components/SessionBoundary.tsx`
- Create: `frontend/src/components/SessionBoundary.test.tsx`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/components/AppShell.tsx`
- Modify: `frontend/src/components/AppShell.test.tsx`
- Modify: `frontend/src/components/TaxToolSettings.tsx`
- Modify: `frontend/src/pages/CalendarPage.test.tsx`
- Modify: `frontend/src/test/render.tsx`
- Modify: `frontend/e2e/critical-flows.spec.ts`

**Interfaces:**
- Consumes: existing `apiRequest`, global `QueryClient`, and React Router.
- Produces: `notifyUnauthorized(): void`, `subscribeUnauthorized(listener): () => void`, `<SessionBoundary>`, and reminder parsing that filters blanks before integer conversion.

- [ ] **Step 1: Write failing 401 and cache-clearing tests**

Create `frontend/src/api/client.test.ts`:

```typescript
import { vi } from "vitest";

import { apiRequest } from "./client";
import { subscribeUnauthorized } from "./session";
import { jsonResponse } from "../test/render";

it("notifies the session boundary for every 401 response", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      jsonResponse(
        { code: "authentication_required", message: "请先登录", details: {} },
        401,
      ),
    ),
  );
  const listener = vi.fn();
  const unsubscribe = subscribeUnauthorized(listener);
  await expect(apiRequest("/api/regions")).rejects.toMatchObject({ status: 401 });
  expect(listener).toHaveBeenCalledOnce();
  unsubscribe();
});
```

Create `frontend/src/components/SessionBoundary.test.tsx`:

```tsx
import { act, screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";

import { notifyUnauthorized } from "../api/session";
import { renderWithProviders } from "../test/render";
import { SessionBoundary } from "./SessionBoundary";

it("clears cached business data and replaces the route on unauthorized", async () => {
  const { queryClient } = renderWithProviders(
    <SessionBoundary>
      <Routes>
        <Route path="/private" element={<h1>私有数据</h1>} />
        <Route path="/login" element={<h1>登录 PreFine</h1>} />
      </Routes>
    </SessionBoundary>,
    "/private",
  );
  queryClient.setQueryData(["sensitive"], { amount: "1.00" });
  act(() => notifyUnauthorized());
  expect(await screen.findByRole("heading", { name: "登录 PreFine" })).toBeVisible();
  expect(queryClient.getQueryData(["sensitive"])).toBeUndefined();
});
```

Extend `renderWithProviders` to return the Testing Library result plus its `queryClient`:

```typescript
const result = render(/* existing providers */);
return { ...result, queryClient };
```

- [ ] **Step 2: Add failing logout/back and reminder normalization tests**

In `frontend/src/components/AppShell.test.tsx`, add:

```tsx
it("clears authenticated queries after logout", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
  const user = userEvent.setup();
  const { queryClient } = renderWithProviders(
    <Routes>
      <Route
        path="/private"
        element={<AppShell><h1>私有数据</h1></AppShell>}
      />
      <Route path="/login" element={<h1>登录 PreFine</h1>} />
    </Routes>,
    "/private",
  );
  queryClient.setQueryData(["tax-settings"], { reminder_days: [7, 3, 1] });
  await user.click(screen.getByRole("button", { name: "退出登录" }));
  expect(await screen.findByRole("heading", { name: "登录 PreFine" })).toBeVisible();
  expect(queryClient.getQueryData(["tax-settings"])).toBeUndefined();
});
```

Add the required `Routes`, `Route`, `userEvent`, and `vi` imports.

Extend `mockApi` with an optional `normalizedReminderDays` and return it from successful PUT responses. Add:

```tsx
it("filters blank reminder tokens and adopts the normalized server value", async () => {
  const fetchMock = mockApi({ normalizedReminderDays: [3, 7] });
  vi.stubGlobal("fetch", fetchMock);
  const user = userEvent.setup();
  renderWithProviders(<CalendarPage />);
  const panel = await screen.findByRole("region", { name: "税务工具设置" });
  const reminderInput = within(panel).getByLabelText("提前提醒天数");
  await user.clear(reminderInput);
  await user.type(reminderInput, "7, ,3,");
  await user.click(within(panel).getByRole("button", { name: "保存税务设置" }));
  const putCall = fetchMock.mock.calls.find(
    ([url, init]) => url === "/api/tools/tax/settings" && init?.method === "PUT",
  );
  expect(JSON.parse(String(putCall?.[1]?.body)).reminder_days).toEqual([7, 3]);
  expect(await within(panel).findByText("设置已保存")).toBeVisible();
  expect(reminderInput).toHaveValue("3,7");
});
```

Add this Playwright regression:

```typescript
test("@desktop logout prevents browser back from restoring private data", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "金额大小写转换" }).click();
  await expect(page.getByRole("heading", { name: "金额大小写转换" })).toBeVisible();
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(page.getByRole("heading", { name: "登录 PreFine" })).toBeVisible();
  await page.goBack();
  await expect(page.getByRole("heading", { name: "登录 PreFine" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "金额大小写转换" })).toHaveCount(0);
});
```

- [ ] **Step 3: Run the new frontend tests and verify RED**

Run:

```powershell
& 'C:\Users\Thou\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd' --dir frontend exec vitest run src/api/client.test.ts src/components/SessionBoundary.test.tsx src/components/AppShell.test.tsx src/pages/CalendarPage.test.tsx
```

Expected: new modules are missing, logout retains cached data, and blank reminder tokens become zero or fail to reflect server normalization.

- [ ] **Step 4: Implement the framework-independent unauthorized event**

Create `frontend/src/api/session.ts`:

```typescript
type UnauthorizedListener = () => void;

const listeners = new Set<UnauthorizedListener>();

export function subscribeUnauthorized(listener: UnauthorizedListener) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function notifyUnauthorized() {
  for (const listener of listeners) listener();
}
```

In `frontend/src/api/client.ts`, before throwing the parsed `ApiError`, call `notifyUnauthorized()` whenever `response.status === 401`.

- [ ] **Step 5: Implement the React session boundary and explicit logout cleanup**

Create `frontend/src/components/SessionBoundary.tsx`:

```tsx
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { subscribeUnauthorized } from "../api/session";

export function SessionBoundary({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  useEffect(
    () =>
      subscribeUnauthorized(() => {
        queryClient.removeQueries();
        navigate("/login", { replace: true });
      }),
    [navigate, queryClient],
  );

  return children;
}
```

Wrap `<App />` inside this component in `frontend/src/main.tsx`. In `AppShell`, obtain `useQueryClient()` and, after a successful logout response, run `queryClient.clear()` before `navigate("/login", { replace: true })`. Keep failed-login mutation state untouched so its message and password field remain visible.

- [ ] **Step 6: Implement raw reminder text and server-authoritative success**

In `TaxToolSettings.tsx`, add:

```typescript
function parseReminderDays(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item !== "")
    .map(Number)
    .filter(Number.isInteger);
}

const [reminderDaysInput, setReminderDaysInput] = useState(() =>
  settings.reminder_days.join(","),
);
```

Use `reminderDaysInput` as the input value. Its change handler only calls `setReminderDaysInput(event.target.value)`. Submit this payload:

```typescript
save.mutate({
  ...draft,
  reminder_days: parseReminderDays(reminderDaysInput),
});
```

On success, run:

```typescript
const normalized = editable(saved);
setDraft(normalized);
setReminderDaysInput(saved.reminder_days.join(","));
setMessage("设置已保存");
onSaved(saved);
```

On failure, reset both `draft` and `reminderDaysInput` from the last server-confirmed `settings` prop.

- [ ] **Step 7: Run Task 3 verification and commit**

Run:

```powershell
& 'C:\Users\Thou\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd' --dir frontend run lint
& 'C:\Users\Thou\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd' --dir frontend exec vitest run
& 'C:\Users\Thou\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd' --dir frontend run build
$env:E2E_PYTHON = (Resolve-Path '.venv\Scripts\python.exe'); $env:PLAYWRIGHT_CHANNEL = 'chrome'; & 'C:\Users\Thou\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd' --dir frontend exec playwright test
```

Expected: lint/build exit 0, all Vitest tests pass, and desktop/mobile Playwright projects including logout/back pass.

Commit:

```powershell
git add frontend/src frontend/e2e/critical-flows.spec.ts
git commit -m "fix(frontend): isolate authenticated session data"
```

---

### Task 4: Gated Image and GitHub Release Workflow

**Files:**
- Create: `docker/smoke-test.sh`
- Replace: `.github/workflows/publish-container.yml`
- Modify: `backend/tests/test_container_distribution.py`

**Interfaces:**
- Consumes: Dockerfile, `/api/health`, `/api/auth/login`, `/api/tools/tax/settings`, and Task 1 same-origin policy.
- Produces: ordered jobs `validate_ref -> verify_source -> smoke_image -> publish_image -> publish_release`; `docker/smoke-test.sh IMAGE` exits nonzero on any runtime contract failure.

- [ ] **Step 1: Write failing workflow contracts**

Refactor workflow tests to parse job blocks and assert:

```python
assert "uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97" in workflow
assert "uses: actions/setup-node@820762786026740c76f36085b0efc47a31fe5020" in workflow
assert "python -m pytest backend/tests" in workflow
assert "python -m ruff check backend" in workflow
assert "python -m pip_audit" in workflow
assert "gitleaks git --redact" in workflow
assert "pnpm --dir frontend audit --prod --audit-level high" in workflow
assert "pnpm --dir frontend exec playwright" in workflow
assert workflow.index("needs: verify_source") < workflow.index("needs: smoke_image")
assert workflow.index("Verify multi-architecture manifest") < workflow.index("gh release create")
assert "permissions:\n      contents: write" in release_job
assert "permissions:\n      contents: read\n      packages: write" in image_job
assert "--verify-tag" in release_job
assert "--generate-notes" in release_job
```

Add contract assertions for `docker/smoke-test.sh`: `set -Eeuo pipefail`, `trap cleanup EXIT`, non-root PID 1 check, health, login, PUT settings with `Origin`, restart, and persistence readback.

- [ ] **Step 2: Run the workflow contract test and verify RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_container_distribution.py -q
```

Expected: failures for missing source gates, smoke script, job permissions, and GitHub Release step.

- [ ] **Step 3: Create the real-image smoke script**

Create executable `docker/smoke-test.sh` with this behavior:

```bash
#!/usr/bin/env bash
set -Eeuo pipefail

image="${1:?usage: smoke-test.sh IMAGE}"
smoke_dir="$(mktemp -d "${RUNNER_TEMP:-/tmp}/prefine-smoke.XXXXXX")"
container="prefine-smoke-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}"
cookie_jar="$smoke_dir/cookies.txt"

cleanup() {
  docker rm --force "$container" >/dev/null 2>&1 || true
  rm -rf "$smoke_dir"
}
trap cleanup EXIT

docker run --detach --name "$container" \
  --publish 127.0.0.1::8000 \
  --env PUID="$(id -u)" \
  --env PGID="$(id -g)" \
  --env ADMIN_USERNAME=admin \
  --env ADMIN_PASSWORD=ci-smoke-password-2026 \
  --env SESSION_SECRET=ci-smoke-session-secret-0123456789abcdef \
  --env DATA_DIR=/data \
  --volume "$smoke_dir:/data" \
  "$image" >/dev/null

port="$(docker port "$container" 8000/tcp | sed -n 's/.*://p')"
base_url="http://127.0.0.1:$port"

wait_for_health() {
  for _ in $(seq 1 60); do
    if curl --fail --silent "$base_url/api/health" | jq -e '.status == "ok"' >/dev/null; then
      return 0
    fi
    sleep 2
  done
  docker logs "$container"
  return 1
}

wait_for_health
test "$(docker exec "$container" awk '/^Uid:/{print $2}' /proc/1/status)" != "0"
test -s "$smoke_dir/prefine.db"

curl --fail --silent --cookie-jar "$cookie_jar" \
  --header 'Content-Type: application/json' \
  --data '{"username":"admin","password":"ci-smoke-password-2026"}' \
  "$base_url/api/auth/login" >/dev/null

curl --fail --silent --cookie "$cookie_jar" \
  --header 'Content-Type: application/json' \
  --header "Origin: $base_url" \
  --request PUT \
  --data '{"default_mode":"personalized","taxpayer_type":"general_taxpayer","selected_item_codes":["vat"],"default_region_code":"111000000","reminder_days":[9,4]}' \
  "$base_url/api/tools/tax/settings" | jq -e '.reminder_days == [9,4]' >/dev/null

docker restart "$container" >/dev/null
wait_for_health
curl --fail --silent --cookie-jar "$cookie_jar" \
  --header 'Content-Type: application/json' \
  --data '{"username":"admin","password":"ci-smoke-password-2026"}' \
  "$base_url/api/auth/login" >/dev/null
curl --fail --silent --cookie "$cookie_jar" \
  "$base_url/api/tools/tax/settings" | jq -e '.reminder_days == [9,4]' >/dev/null
```

Set mode `0755` in Git.

- [ ] **Step 4: Replace the workflow with five least-privilege jobs**

Replace `.github/workflows/publish-container.yml` with this complete structure:

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

concurrency:
  group: prefine-container-${{ github.ref }}
  cancel-in-progress: false

env:
  IMAGE_NAME: ghcr.io/thougyeongcho/prefine

jobs:
  validate_ref:
    if: github.event_name != 'workflow_dispatch' || github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - name: Validate publication ref
        shell: bash
        run: |
          set -euo pipefail
          if [ "$GITHUB_REF" = "refs/heads/main" ]; then
            exit 0
          fi
          [[ "$GITHUB_REF" =~ ^refs/tags/v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]

  verify_source:
    needs: validate_ref
    runs-on: ubuntu-latest
    steps:
      - name: Check out complete history
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0
        with:
          python-version: "3.12"

      - name: Set up Node
        uses: actions/setup-node@820762786026740c76f36085b0efc47a31fe5020 # v7.0.0
        with:
          node-version: "22"

      - name: Install backend verification tools
        run: python -m pip install '.[dev]' 'pip-audit==2.10.1'

      - name: Verify backend
        run: |
          set -euo pipefail
          python -m pytest backend/tests
          python -m ruff check backend
          python -m pip_audit

      - name: Install frontend dependencies
        shell: bash
        run: |
          set -euo pipefail
          corepack enable
          corepack prepare pnpm@11.9.0 --activate
          pnpm --dir frontend install --frozen-lockfile

      - name: Audit and verify frontend
        shell: bash
        run: |
          set -euo pipefail
          pnpm --dir frontend audit --prod --audit-level high
          pnpm --dir frontend run lint
          pnpm --dir frontend exec vitest run
          pnpm --dir frontend run build
          pnpm --dir frontend exec playwright install --with-deps chromium
          pnpm --dir frontend exec playwright test

      - name: Scan complete history for secrets
        shell: bash
        run: |
          set -euo pipefail
          version=8.30.1
          archive="gitleaks_${version}_linux_x64.tar.gz"
          checksums="gitleaks_${version}_checksums.txt"
          base="https://github.com/gitleaks/gitleaks/releases/download/v${version}"
          curl --fail --silent --show-error --location --remote-name "$base/$archive"
          curl --fail --silent --show-error --location --remote-name "$base/$checksums"
          grep "  $archive$" "$checksums" | sha256sum --check --strict -
          tar --extract --gzip --file "$archive" gitleaks
          ./gitleaks git --redact --verbose --config .gitleaks.toml

  smoke_image:
    needs: verify_source
    runs-on: ubuntu-latest
    steps:
      - name: Check out repository
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@bb05f3f5519dd87d3ba754cc423b652a5edd6d2c # v4.2.0

      - name: Build smoke image without pushing
        uses: docker/build-push-action@53b7df96c91f9c12dcc8a07bcb9ccacbed38856a # v7.3.0
        with:
          context: .
          platforms: linux/amd64
          load: true
          tags: prefine:smoke
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Verify runtime, migration, login and persistence
        run: docker/smoke-test.sh prefine:smoke

  publish_image:
    needs: smoke_image
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
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

  publish_release:
    needs: publish_image
    if: startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - name: Check out complete tags
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          fetch-depth: 0

      - name: Create synchronized GitHub Release
        shell: bash
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          set -euo pipefail
          tag="$GITHUB_REF_NAME"
          test "$(git rev-list -n 1 "$tag")" = "$GITHUB_SHA"
          if gh release view "$tag" --json tagName,isDraft,isPrerelease >release.json 2>/dev/null; then
            jq -e --arg tag "$tag" \
              '.tagName == $tag and .isDraft == false and .isPrerelease == false' \
              release.json >/dev/null
            exit 0
          fi
          version="${tag#v}"
          notes="$(printf '%s\n\n%s\n\n%s\n' \
            '## Docker' \
            "\`docker pull ghcr.io/thougyeongcho/prefine:$version\`" \
            "[Compose 部署](https://github.com/$GITHUB_REPOSITORY/blob/$tag/README.md) · [升级与恢复](https://github.com/$GITHUB_REPOSITORY/blob/$tag/docs/operations.md)")"
          gh release create "$tag" \
            --verify-tag \
            --title "$tag" \
            --generate-notes \
            --notes "$notes" \
            --latest
```

- [ ] **Step 5: Run Task 4 local non-Docker verification and commit**

Run only contract/static checks locally; do not build an image:

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_container_distribution.py -q
.venv\Scripts\python.exe -m ruff check backend
```

Expected: workflow ordering, permissions, pins, tag rules, smoke coverage, and Release ordering tests all pass.

Commit:

```powershell
git add .github/workflows/publish-container.yml docker/smoke-test.sh backend/tests/test_container_distribution.py
git commit -m "ci(release): gate images and github releases"
```

---

### Task 5: Public License, Security, and Fail-Closed Operations

**Files:**
- Create: `LICENSE`
- Create: `SECURITY.md`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `docs/operations.md`
- Modify: `AGENTS.md`
- Modify: `backend/tests/test_container_distribution.py`
- Modify: `backend/tests/test_acceptance_contracts.py`

**Interfaces:**
- Consumes: Task 1 `TRUSTED_PROXY_IPS`, Task 2 maintenance commands, Task 4 version/Release behavior.
- Produces: copy-safe but intentionally non-startable `.env.example`, exact public operations, MIT license, and private vulnerability reporting instructions.

- [ ] **Step 1: Write failing public-document contracts**

Assert in backend contract tests:

```python
assert "ADMIN_PASSWORD=CHANGE_ME_ADMIN_PASSWORD" in env_example
assert "SESSION_SECRET=CHANGE_ME_SESSION_SECRET" in env_example
assert "TRUSTED_PROXY_IPS=" in env_example
assert "Copyright (c) 2026 ThouGyeongcho" in license_text
assert "MIT License" in license_text
assert "security/advisories/new" in security_text
assert "python -m backend.app.database_maintenance backup" in operations
assert "python -m backend.app.database_maintenance restore prefine-20260722T120000Z.db" in operations
assert operations.count("set -eu") >= 2
assert '$ErrorActionPreference = "Stop"' in operations
assert "docker compose ps --status running --services" in operations
assert "docker compose pull" in readme
assert "GitHub Release" in readme
```

Delete old tests that require direct host `cp`/`Copy-Item` database overwrites.

- [ ] **Step 2: Run document contract tests and verify RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_container_distribution.py backend/tests/test_acceptance_contracts.py -q
```

Expected: failures for missing license/security files, valid example credentials, and unsafe copy-based operations.

- [ ] **Step 3: Add exact MIT and security documents**

Create `LICENSE` with the canonical MIT text and exact heading/copyright:

```text
MIT License

Copyright (c) 2026 ThouGyeongcho

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

Create `SECURITY.md`:

```markdown
# Security Policy

## Supported versions

Security fixes are provided for the latest published `0.x` release of PreFine.

## Reporting a vulnerability

Do not disclose security vulnerabilities in a public issue.

Use [GitHub private vulnerability reporting](https://github.com/ThouGyeongcho/PreFine/security/advisories/new) to send a private report. Include the affected version, reproduction steps, impact, and any suggested mitigation. Maintainers will acknowledge the report through the private advisory and coordinate disclosure after a fix is available.
```

- [ ] **Step 4: Make example configuration intentionally non-startable**

Set in `.env.example`:

```dotenv
ADMIN_USERNAME=admin
ADMIN_PASSWORD=CHANGE_ME_ADMIN_PASSWORD
SESSION_SECRET=CHANGE_ME_SESSION_SECRET
TRUSTED_PROXY_IPS=
```

Document that single-layer reverse proxies must be listed by exact direct IP and must overwrite `X-Forwarded-For` with one client IP. Keep empty as the secure default.

- [ ] **Step 5: Replace host-copy backup/restore documentation**

Use fail-fast POSIX examples beginning with:

```sh
set -eu
docker compose stop app
if docker compose ps --status running --services | grep -qx app; then
  echo "PreFine app is still running; maintenance aborted" >&2
  exit 1
fi
docker compose run --rm --no-deps app \
  python -m backend.app.database_maintenance backup
docker compose start app
curl --fail http://localhost:8000/api/health
```

The complete POSIX restore example is:

```sh
set -eu
docker compose stop app
if docker compose ps --status running --services | grep -qx app; then
  echo "PreFine app is still running; maintenance aborted" >&2
  exit 1
fi
docker compose run --rm --no-deps app \
  python -m backend.app.database_maintenance restore prefine-20260722T120000Z.db
docker compose start app
curl --fail http://localhost:8000/api/health
```

Use the concrete restore example `prefine-20260722T120000Z.db`. The PowerShell backup example is:

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

The complete PowerShell restore example is:

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

Explain that backups live inside `${PREFINE_DATA_DIR}/backups`, restore automatically writes a validated `pre-restore-*` backup, and failed maintenance intentionally leaves the application stopped.

- [ ] **Step 6: Update README and repository guidance**

Keep the README Compose block byte-for-byte equal to `docker-compose.yml`. Add links to GitHub Releases, GHCR, MIT, SECURITY, backup/restore, and the rule that only semantic version tags create Releases while `latest` follows `main`.

Update `AGENTS.md` to remove “manifests are not yet present”, replace local `docker compose up --build` with pull-only commands, and state that Docker builds run only in GitHub Actions.

- [ ] **Step 7: Run Task 5 verification and commit**

Run:

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_container_distribution.py backend/tests/test_acceptance_contracts.py backend/tests/test_prefine_identity.py -q
.venv\Scripts\python.exe -m ruff check backend
```

Expected: documents, exact Compose, identity, license, security, and maintenance contracts pass.

Commit:

```powershell
git add LICENSE SECURITY.md .env.example README.md docs/operations.md AGENTS.md backend/tests
git commit -m "docs(public): add safe deployment and licensing"
```

---

### Task 6: Full Verification, Private Publication Gate, and v0.1.0

**Files:**
- Verify all tracked files and Git history.
- No implementation file changes unless a preceding verification exposes a regression; any fix must return to the owning task's RED/GREEN cycle and receive a separate commit.

**Interfaces:**
- Consumes: all five reviewed task commits.
- Produces: clean private `main`, successful private `latest` workflow, public repository and GHCR, anonymous image access, immutable `v0.1.0`, synchronized GitHub Release, and two dual-architecture manifests.

- [ ] **Step 1: Run the complete local non-Docker gate**

Run from a clean shell:

```powershell
.venv\Scripts\python.exe -m pytest backend/tests
.venv\Scripts\python.exe -m ruff check backend
.venv\Scripts\python.exe -m pip_audit
& 'C:\Users\Thou\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd' --dir frontend run lint
& 'C:\Users\Thou\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd' --dir frontend exec vitest run
& 'C:\Users\Thou\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd' --dir frontend run build
$env:E2E_PYTHON = (Resolve-Path '.venv\Scripts\python.exe'); $env:PLAYWRIGHT_CHANNEL = 'chrome'; & 'C:\Users\Thou\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd' --dir frontend exec playwright test
& 'C:\Users\Thou\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd' --dir frontend audit --prod --audit-level high
```

Expected: every command exits 0. Do not run `docker build`, `docker compose build`, or any local image build.

- [ ] **Step 2: Repeat secret, history, and publication-state checks**

Run Gitleaks 8.30.1 against the complete reachable repository with `.gitleaks.toml`. Enumerate tracked paths and all refs to prove there are no `.env`, database, dependency, build, test-report, or six removed branding process images. Confirm the final Logo SHA-256 is still:

```text
ac9901d5c3dac3d3b67b287f2d63c050465066c609aa269ec619200409992df7
```

Use `gh repo view ThouGyeongcho/PreFine --json visibility` and package metadata to confirm both repository and GHCR are still private before pushing.

- [ ] **Step 3: Request final code review and resolve every blocking finding**

Review the full diff from `920ca9c` through HEAD against the approved design. A Critical or Important finding returns to its owning task for a regression test and fix. Re-run Step 1 after any change. Proceed only with an explicit “ready to publish” review result.

- [ ] **Step 4: Push private main and wait for the updated private workflow**

Verify local `main` is ahead of the frozen private remote only by intended commits, then perform a normal push without force. Watch the new workflow through `validate_ref`, `verify_source`, `smoke_image`, and `publish_image`. For the main run, assert `publish_release` is skipped and private `latest` has amd64 and arm64.

- [ ] **Step 5: Perform the final remote safety audit**

Confirm remote `main` equals local HEAD, all remote refs are expected, Gitleaks passes against freshly fetched remote history, the six removed images have zero reachable commits, and only the final Logo remains. Do not change visibility if any check differs.

- [ ] **Step 6: Make the source public and enable private vulnerability reporting**

Execute the GitHub visibility change only after Step 5. Immediately enable private vulnerability reporting and verify an unauthenticated request can read the repository and `SECURITY.md`.

- [ ] **Step 7: Make GHCR public and verify anonymous latest access**

Change only the `prefine` container package to public. Without an authenticated header, request an anonymous GHCR pull token for `repository:thougyeongcho/prefine:pull`, fetch the `latest` OCI manifest, and verify it contains amd64 and arm64 descriptors. Treat public package visibility as irreversible.

- [ ] **Step 8: Create the immutable first version tag**

Confirm no local or remote `v0.1.0` exists and HEAD is still the verified remote `main`. Create one annotated tag and push only that tag:

```powershell
git tag -a v0.1.0 -m "PreFine v0.1.0"
git push origin refs/tags/v0.1.0
```

Never move or force-update this tag.

- [ ] **Step 9: Verify synchronized image and GitHub Release**

Wait for the tag workflow to pass every job. Verify:

- `ghcr.io/thougyeongcho/prefine:0.1.0` is anonymously accessible.
- Its manifest contains `linux/amd64` and `linux/arm64`.
- GitHub Release `v0.1.0` exists, is neither draft nor prerelease, is marked latest, contains the exact Docker pull command, and points to the same commit as the tag and OCI revision label.
- `latest` remains available and no `0.1` or `0` tags exist.
- Local worktree is clean and `main` equals `origin/main`.

- [ ] **Step 10: Record the release outcome**

Report the public repository URL, Release URL, GHCR package URL, final main SHA, tag SHA, manifest platforms, anonymous verification result, exact tests/audits run, and the off-workspace recovery bundle location and checksum. Do not delete the recovery bundle unless the user separately requests it.
