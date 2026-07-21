# Finance Toolkit v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved single-user finance toolkit v1 with secure login, strict RMB conversion, cached 12366 tax calendars, personalized tax filtering, email reminders, a responsive React interface, and single-container deployment.

**Architecture:** FastAPI owns authenticated JSON APIs, SQLite persistence, scheduled synchronization, reminder delivery, and the production React bundle. Business logic remains in focused modules that do not depend on routes; upstream 12366 access is isolated behind a validated adapter; the React client consumes stable `snake_case` contracts through TanStack Query.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, HTTPX, APScheduler, aiosmtplib, pytest, Ruff, React, TypeScript, Vite, React Router, TanStack Query, Vitest, React Testing Library, Playwright, Docker.

## Global Constraints

- Use `Decimal` for every monetary value; binary floating point must not participate in money calculations.
- Preserve upstream `bssz` text, event order, and dates exactly in the official calendar view.
- Unmapped personalized tax items must appear as `其他待确认` and retain their official text and dates.
- All business APIs require the single administrator session except `/api/health` and `/api/auth/login`.
- Sessions expire after 12 hours; cookies are `HttpOnly`, `SameSite=Lax`, and conditionally `Secure`.
- SQLite uses WAL, foreign keys, and a busy timeout; migrations run before the application starts.
- The final image runs one Uvicorn worker as a non-root user and persists `/data/finance-toolkit.db`.
- Tool-local settings remain inside the owning tool interface; secrets are environment-only and never returned or logged.
- The current workspace is not a Git repository, so commit steps are recorded but cannot run until Git is initialized.

## File Map

- `backend/app/config.py`: validated environment configuration and secret-safe status helpers.
- `backend/app/db.py`, `backend/app/models.py`: SQLite engine/session lifecycle and persisted entities.
- `backend/app/main.py`, `backend/app/api.py`, `backend/app/errors.py`: application lifecycle, routing, static hosting, and stable errors.
- `backend/app/money.py`: framework-free strict RMB parsing and encoding.
- `backend/app/auth.py`: login throttling, signed sessions, cookie/origin enforcement.
- `backend/app/tax_source.py`: region seed data and validated 12366 responses.
- `backend/app/calendar.py`: cached month reads, synchronization, freshness, and replacement.
- `backend/app/tax_profile.py`: settings validation, catalog mapping, and personalized filtering.
- `backend/app/reminders.py`: due-date grouping, email composition, SMTP delivery, and deduplication.
- `backend/app/scheduler.py`: single-process scheduled sync and reminder orchestration.
- `backend/migrations/`: Alembic configuration and initial schema.
- `frontend/src/api/`: typed API client and contracts.
- `frontend/src/components/`: reusable shell, status, forms, and calendar components.
- `frontend/src/pages/`: login, dashboard, money, calendar, and system-status pages.
- `frontend/e2e/`: authenticated critical-path acceptance tests.
- `Dockerfile`, `docker-compose.yml`, `docker/entrypoint.sh`: production build and startup.

---

### Task 1: Backend foundation, configuration, persistence, and health

**Files:**
- Create: `pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`
- Create: `backend/app/db.py`
- Create: `backend/app/models.py`
- Create: `backend/app/errors.py`
- Create: `backend/app/main.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_health.py`
- Create: `backend/alembic.ini`
- Create: `backend/migrations/env.py`
- Create: `backend/migrations/versions/20260721_0001_initial.py`

**Interfaces:**
- Produces: `Settings`, `get_settings()`, `Database`, `create_app()`, and the six approved SQLite tables.
- Produces: `GET /api/health -> {status, database, scheduler, version}` without secrets.

- [x] **Step 1: Write failing configuration and health tests**

```python
def test_required_secrets_are_validated():
    with pytest.raises(ValidationError):
        Settings(ADMIN_USERNAME="admin", ADMIN_PASSWORD="secret", SESSION_SECRET="short")


def test_health_does_not_require_authentication(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "scheduler": "stopped",
        "version": "0.1.0",
    }
```

- [x] **Step 2: Run the tests and confirm the missing-module failure**

Run: `python -m pytest backend/tests/test_health.py -v`

Expected: FAIL because `backend.app.config` and `backend.app.main` do not exist.

- [x] **Step 3: Implement validated settings, SQLite pragmas, initial models, stable errors, and the health route**

```python
class Settings(BaseSettings):
    admin_username: str = Field(alias="ADMIN_USERNAME", min_length=1)
    admin_password: SecretStr = Field(alias="ADMIN_PASSWORD", min_length=1)
    session_secret: SecretStr = Field(alias="SESSION_SECRET", min_length=32)
    data_dir: Path = Field(default=Path("/data"), alias="DATA_DIR")
    cookie_secure: bool = Field(default=False, alias="COOKIE_SECURE")
    timezone: str = Field(default="Asia/Shanghai", alias="TZ")


@event.listens_for(engine, "connect")
def configure_sqlite(connection: sqlite3.Connection, _: object) -> None:
    cursor = connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()
```

The migration creates `calendar_events`, `calendar_sync_state`, `tax_catalog_items`, `tax_catalog_aliases`, `tool_settings`, and `email_dispatches` with the unique keys defined in the approved spec.

- [x] **Step 4: Verify the task**

Run: `python -m pytest backend/tests/test_health.py -v`

Expected: PASS.

Run: `ruff check backend`

Expected: no diagnostics.

- [x] **Step 5: Record the intended commit**

`feat(core): scaffold backend persistence and health`

---

### Task 2: Strict RMB conversion domain and APIs

**Files:**
- Create: `backend/app/money.py`
- Create: `backend/app/api.py`
- Create: `backend/tests/test_money.py`
- Create: `backend/tests/test_money_api.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Produces: `parse_amount(value: str) -> Decimal`, `to_uppercase(value: Decimal) -> str`, `from_uppercase(value: str) -> Decimal`, `format_amount(value: Decimal) -> str`.
- Produces: `POST /api/money/to-uppercase` and `POST /api/money/to-number`.

- [x] **Step 1: Write failing table-driven domain tests**

```python
@pytest.mark.parametrize(
    ("raw", "normalized", "uppercase"),
    [
        ("0", "0.00", "零元整"),
        ("-0.00", "0.00", "零元整"),
        ("1", "1.00", "壹元整"),
        ("10.01", "10.01", "壹拾元零壹分"),
        ("1001.10", "1001.10", "壹仟零壹元壹角"),
        ("-128650.32", "-128650.32", "负壹拾贰万捌仟陆佰伍拾元叁角贰分"),
        ("999,999,999,999,999.99", "999999999999999.99", "玖佰玖拾玖万玖仟玖佰玖拾玖亿玖仟玖佰玖拾玖万玖仟玖佰玖拾玖元玖角玖分"),
    ],
)
def test_round_trip(raw: str, normalized: str, uppercase: str):
    amount = parse_amount(raw)
    assert format_amount(amount) == normalized
    assert to_uppercase(amount) == uppercase
    assert from_uppercase(uppercase) == amount


@pytest.mark.parametrize("raw", ["1.001", "1e3", "￥1", " 1", "1,00", "1,2345", "1 000"])
def test_rejects_noncanonical_numeric_input(raw: str):
    with pytest.raises(MoneyFormatError):
        parse_amount(raw)


@pytest.mark.parametrize("raw", ["人民币壹元整", "一元整", "壹圆整", "壹元正", "壹元"])
def test_rejects_noncanonical_uppercase_input(raw: str):
    with pytest.raises(MoneyFormatError):
        from_uppercase(raw)
```

- [x] **Step 2: Confirm the tests fail**

Run: `python -m pytest backend/tests/test_money.py -v`

Expected: FAIL because the domain functions do not exist.

- [x] **Step 3: Implement regex validation, integer-section encoding, jiao/fen encoding, and strict round-trip parsing**

```python
AMOUNT_PATTERN = re.compile(r"^-?(?:0|[1-9]\d*|[1-9]\d{0,2}(?:,\d{3})+)(?:\.\d{1,2})?$")
MAX_AMOUNT = Decimal("999999999999999.99")


def parse_amount(value: str) -> Decimal:
    if not AMOUNT_PATTERN.fullmatch(value):
        raise MoneyFormatError("请输入规范数字，最多保留两位小数")
    amount = Decimal(value.replace(",", ""))
    if abs(amount) > MAX_AMOUNT:
        raise MoneyFormatError("金额超出支持范围")
    return Decimal("0.00") if amount == 0 else amount.quantize(Decimal("0.01"))


def from_uppercase(value: str) -> Decimal:
    parsed = _parse_uppercase_components(value)
    if to_uppercase(parsed) != value:
        raise MoneyFormatError("请输入系统生成的规范人民币大写")
    return parsed
```

- [x] **Step 4: Add authenticated API contract tests and routes**

```python
def test_to_uppercase_api(authenticated_client):
    response = authenticated_client.post("/api/money/to-uppercase", json={"amount": "-128650.32"})
    assert response.status_code == 200
    assert response.json() == {
        "amount": "-128650.32",
        "uppercase": "负壹拾贰万捌仟陆佰伍拾元叁角贰分",
    }


def test_three_decimal_places_returns_stable_error(authenticated_client):
    response = authenticated_client.post("/api/money/to-uppercase", json={"amount": "1.001"})
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_money_format"
```

- [x] **Step 5: Verify the task**

Run: `python -m pytest backend/tests/test_money.py backend/tests/test_money_api.py -v`

Expected: PASS.

- [x] **Step 6: Record the intended commit**

`feat(money): add strict bidirectional RMB conversion`

---

### Task 3: Single-administrator authentication and request protection

**Files:**
- Create: `backend/app/auth.py`
- Create: `backend/tests/test_auth.py`
- Modify: `backend/app/api.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Produces: `SessionPrincipal`, `require_session(request)`, `require_same_origin(request)`, and login-attempt storage.
- Produces: `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`.

- [x] **Step 1: Write failing tests for credentials, throttling, expiration, cookie flags, unauthorized APIs, and origin rejection**

```python
def test_login_sets_secure_session_cookie(client):
    response = client.post("/api/auth/login", json={"username": "admin", "password": "correct"})
    assert response.status_code == 204
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Max-Age=43200" in cookie


def test_sixth_failed_login_is_rate_limited(client):
    for _ in range(5):
        assert client.post("/api/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 429


def test_state_change_rejects_foreign_origin(authenticated_client):
    response = authenticated_client.post(
        "/api/auth/logout",
        headers={"Origin": "https://attacker.example"},
    )
    assert response.status_code == 403
```

- [x] **Step 2: Confirm the tests fail**

Run: `python -m pytest backend/tests/test_auth.py -v`

Expected: FAIL because authentication routes do not exist.

- [x] **Step 3: Implement constant-time credential checks, signed timestamps, per-IP throttling, cookies, and guards**

```python
SESSION_COOKIE = "finance_session"
SESSION_MAX_AGE_SECONDS = 12 * 60 * 60
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_FAILURE_LIMIT = 5


def credentials_match(settings: Settings, username: str, password: str) -> bool:
    username_ok = secrets.compare_digest(username, settings.admin_username)
    password_ok = secrets.compare_digest(password, settings.admin_password.get_secret_value())
    return username_ok and password_ok
```

State-changing cookie-authenticated routes call `require_same_origin`; all business routers depend on `require_session`.

- [x] **Step 4: Verify authentication and existing API regression tests**

Run: `python -m pytest backend/tests/test_auth.py backend/tests/test_money_api.py -v`

Expected: PASS.

- [x] **Step 5: Record the intended commit**

`feat(auth): protect toolkit with administrator sessions`

---

### Task 4: Validated 12366 adapter and offline region seed

**Files:**
- Create: `backend/app/tax_source.py`
- Create: `backend/app/data/regions.json`
- Create: `backend/tests/fixtures/tax_calendar_success.json`
- Create: `backend/tests/fixtures/tax_calendar_empty.json`
- Create: `backend/tests/test_tax_source.py`

**Interfaces:**
- Produces: `Region(code: str, name: str)`, `SourceCalendarEvent`, `TaxSourceClient.fetch_regions()`, and `TaxSourceClient.fetch_month(region_code, month)`.
- Consumes official 12366 endpoints and treats every response as untrusted.

- [x] **Step 1: Write adapter contract tests**

```python
def test_maps_valid_month_without_rewriting_bssz(mock_transport, success_fixture):
    client = TaxSourceClient(transport=mock_transport(success_fixture))
    events = asyncio.run(client.fetch_month("11100000000", YearMonth(2026, 7)))
    assert events[0].bssz == success_fixture["data"][0]["bssz"]


@pytest.mark.parametrize("fixture", ["missing_dates", "invalid_date", "wrong_list_type", "business_failure"])
def test_rejects_malformed_upstream(fixture_loader, fixture):
    with pytest.raises(TaxSourceProtocolError):
        asyncio.run(fixture_loader(fixture).fetch_month("11100000000", YearMonth(2026, 7)))
```

- [x] **Step 2: Confirm failure, then implement timeout and one short backoff retry**

Run: `python -m pytest backend/tests/test_tax_source.py -v`

Expected before implementation: FAIL; expected after implementation: PASS.

```python
response = await self._client.post(
    "/bsfw/calendar/getCalendarListForMonth",
    data={"ssjg": region_code, "bssj": str(month)},
    timeout=10.0,
)
response.raise_for_status()
payload = UpstreamCalendarResponse.model_validate(response.json())
if payload.status_code != "200":
    raise TaxSourceBusinessError("12366 returned a business failure")
```

- [x] **Step 3: Verify all 36 approved region names and codes load offline**

Run: `python -m pytest backend/tests/test_tax_source.py::test_offline_seed_contains_36_regions -v`

Expected: PASS with 36 unique region codes.

- [x] **Step 4: Record the intended commit**

`feat(tax): add validated 12366 source adapter`

---

### Task 5: Calendar caching, synchronization, and APIs

**Files:**
- Create: `backend/app/calendar.py`
- Create: `backend/tests/test_calendar.py`
- Create: `backend/tests/test_calendar_api.py`
- Modify: `backend/app/api.py`
- Modify: `backend/app/models.py`

**Interfaces:**
- Produces: `CalendarService.get_month()`, `sync_month()`, `refresh_in_background()`, and `CalendarMonthResult`.
- Produces: `GET /api/regions`, `GET /api/calendar`, `POST /api/tools/tax/sync`.

- [x] **Step 1: Write failing cache lifecycle tests**

```python
def test_first_read_waits_for_sync(calendar_service, source):
    result = asyncio.run(calendar_service.get_month("11100000000", YearMonth(2026, 7)))
    assert source.call_count == 1
    assert result.stale is False


def test_fresh_cache_avoids_upstream(calendar_service, seeded_fresh_month, source):
    result = asyncio.run(calendar_service.get_month(seeded_fresh_month.region, seeded_fresh_month.month))
    assert source.call_count == 0
    assert result.sync_status == "fresh"


def test_failed_refresh_preserves_official_rows(calendar_service, seeded_stale_month, failing_source):
    before = seeded_stale_month.official_rows()
    result = asyncio.run(calendar_service.sync_month(seeded_stale_month.region, seeded_stale_month.month))
    assert result.sync_status == "failed_using_cache"
    assert seeded_stale_month.official_rows() == before
```

- [x] **Step 2: Confirm failure, then implement transactional replacement and per-key async locks**

Run: `python -m pytest backend/tests/test_calendar.py -v`

Expected before implementation: FAIL; expected after implementation: PASS.

```python
lock = self._locks.setdefault((region_code, str(month)), asyncio.Lock())
async with lock:
    events = await self._source.fetch_month(region_code, month)
    with self._database.session() as session, session.begin():
        session.execute(delete(CalendarEvent).where(CalendarEvent.region_code == region_code, CalendarEvent.cache_month == str(month)))
        session.add_all(self._to_models(region_code, month, events, fetched_at))
        self._mark_success(session, region_code, month, fetched_at)
```

- [x] **Step 3: Add API tests for fresh, stale, failure-with-cache, and no-cache failure responses**

Run: `python -m pytest backend/tests/test_calendar_api.py -v`

Expected: PASS; no-cache upstream failure returns stable code `calendar_unavailable` with HTTP 503.

- [x] **Step 4: Record the intended commit**

`feat(calendar): cache and synchronize monthly tax events`

---

### Task 6: Tax catalog, settings, and personalized filtering

**Files:**
- Create: `backend/app/tax_profile.py`
- Create: `backend/app/data/tax_catalog.json`
- Create: `backend/tests/test_tax_profile.py`
- Create: `backend/tests/test_tax_settings_api.py`
- Modify: `backend/app/api.py`
- Modify: `backend/app/calendar.py`

**Interfaces:**
- Produces: `TaxToolSettings`, `Catalog`, `PersonalizedEvent`, `filter_events(events, settings, catalog)`.
- Produces: `GET /api/tools/tax/settings`, `PUT /api/tools/tax/settings`.

- [x] **Step 1: Write tests for taxpayer scope, selected items, exact aliases, unknown items, empty profiles, and official immutability**

```python
def test_unknown_text_is_visible_for_confirmation(official_event, configured_settings, catalog):
    official_event.bssz = "新出现的上游事项"
    result = filter_events([official_event], configured_settings, catalog)
    assert result[0].category == "其他待确认"
    assert result[0].official_text == "新出现的上游事项"
    assert result[0].start_date == official_event.start_date
    assert result[0].end_date == official_event.end_date


def test_filter_never_mutates_official_bssz(official_event, configured_settings, catalog):
    before = official_event.bssz
    filter_events([official_event], configured_settings, catalog)
    assert official_event.bssz == before
```

- [x] **Step 2: Confirm failure, then implement versioned exact aliases and explicit taxpayer applicability**

Run: `python -m pytest backend/tests/test_tax_profile.py -v`

Expected before implementation: FAIL; expected after implementation: PASS.

```python
class TaxToolSettings(BaseModel):
    default_mode: Literal["official", "personalized"] = "official"
    taxpayer_type: Literal["general_taxpayer", "small_scale_taxpayer"] | None = None
    selected_item_codes: list[str] = []
    default_region_code: str | None = None
    reminder_days: list[int] = [7, 3, 1]

    @field_validator("reminder_days")
    @classmethod
    def valid_reminder_days(cls, values: list[int]) -> list[int]:
        if any(value < 0 or value > 30 for value in values):
            raise ValueError("提醒天数必须在 0 到 30 之间")
        return sorted(set(values), reverse=True)
```

- [x] **Step 3: Add transactional settings API tests**

Run: `python -m pytest backend/tests/test_tax_settings_api.py backend/tests/test_calendar_api.py -v`

Expected: PASS; failed validation leaves stored settings unchanged.

- [x] **Step 4: Record the intended commit**

`feat(tax): add profile-based calendar filtering`

---

### Task 7: Reminder calculation, SMTP delivery, and scheduling

**Files:**
- Create: `backend/app/reminders.py`
- Create: `backend/app/scheduler.py`
- Create: `backend/tests/test_reminders.py`
- Create: `backend/tests/test_scheduler.py`
- Create: `backend/tests/test_test_email_api.py`
- Modify: `backend/app/api.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Produces: `ReminderService.check_due(now)`, `send_test_email()`, recipient fingerprinting, and successful-dispatch deduplication.
- Produces: `POST /api/tools/tax/test-email`.

- [x] **Step 1: Write Beijing-time reminder tests**

```python
@pytest.mark.parametrize("days", [7, 3, 1, 0])
def test_due_offsets_are_selected(days, reminder_service, event_ending_in):
    event = event_ending_in(days)
    messages = asyncio.run(reminder_service.build_due_messages(FROZEN_BEIJING_NOW))
    assert event.official_text in messages[0].body


def test_success_deduplicates_but_smtp_failure_retries(reminder_service, smtp):
    smtp.fail_once()
    first = asyncio.run(reminder_service.check_due(FROZEN_BEIJING_NOW))
    second = asyncio.run(reminder_service.check_due(FROZEN_BEIJING_NOW.plus(hours=1)))
    third = asyncio.run(reminder_service.check_due(FROZEN_BEIJING_NOW.plus(hours=2)))
    assert first.failed == 1
    assert second.sent == 1
    assert third.skipped_duplicate == 1
```

- [x] **Step 2: Confirm failure, then implement grouping and fingerprint-safe persistence**

Run: `python -m pytest backend/tests/test_reminders.py -v`

Expected before implementation: FAIL; expected after implementation: PASS.

```python
def recipient_fingerprint(address: str, secret: bytes) -> str:
    return hmac.new(secret, address.strip().lower().encode(), hashlib.sha256).hexdigest()


def reminder_key(region_code: str, due_date: date, advance_days: int, recipient_hash: str) -> str:
    return f"{region_code}:{due_date.isoformat()}:{advance_days}:{recipient_hash}"
```

- [x] **Step 3: Implement the 08:00 sync job, hourly 09:00-18:00 reminder job, and in-window startup catch-up**

Run: `python -m pytest backend/tests/test_scheduler.py backend/tests/test_test_email_api.py -v`

Expected: PASS; test email does not create an `email_dispatches` business deduplication row.

- [x] **Step 4: Record the intended commit**

`feat(reminders): schedule deduplicated tax deadline emails`

---

### Task 8: React shell, authentication flow, and dashboard

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/styles.css`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/types.ts`
- Create: `frontend/src/components/AppShell.tsx`
- Create: `frontend/src/components/ProtectedRoute.tsx`
- Create: `frontend/src/pages/LoginPage.tsx`
- Create: `frontend/src/pages/DashboardPage.tsx`
- Create: `frontend/src/pages/SystemPage.tsx`
- Create: `frontend/src/pages/LoginPage.test.tsx`
- Create: `frontend/src/components/AppShell.test.tsx`

**Interfaces:**
- Produces: responsive 190px desktop sidebar, mobile drawer, protected routing, login/logout, dashboard tool entries, and deployment status.

- [x] **Step 1: Write failing login and responsive navigation component tests**

```tsx
it('logs in and redirects to the dashboard', async () => {
  renderWithRouter(<LoginPage />, { route: '/login' })
  await user.type(screen.getByLabelText('用户名'), 'admin')
  await user.type(screen.getByLabelText('密码'), 'secret')
  await user.click(screen.getByRole('button', { name: '登录' }))
  expect(await screen.findByRole('heading', { name: '工作台' })).toBeVisible()
})
```

- [x] **Step 2: Confirm the tests fail, then implement the app shell and typed fetch wrapper**

Run: `npm --prefix frontend run test -- --run`

Expected before implementation: FAIL; expected after implementation: PASS.

```ts
export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...init.headers },
  })
  if (!response.ok) throw await ApiError.fromResponse(response)
  return response.status === 204 ? (undefined as T) : response.json()
}
```

- [x] **Step 3: Apply the approved visual tokens and visible keyboard focus**

```css
:root {
  color: #171a20;
  background: #ffffff;
  font-family: Inter, PingFang SC, Microsoft YaHei, sans-serif;
  font-weight: 400;
  --accent: #3e6ae1;
  --surface: #f4f4f4;
  --divider: #eeeeee;
  --divider-strong: #d0d1d2;
  --muted: #5c5e62;
}

:focus-visible { outline: 2px solid #3e6ae1; outline-offset: 2px; }
```

- [x] **Step 4: Record the intended commit**

`feat(frontend): add authenticated responsive application shell`

---

### Task 9: Money converter interface

**Files:**
- Create: `frontend/src/pages/MoneyPage.tsx`
- Create: `frontend/src/pages/MoneyPage.test.tsx`
- Modify: `frontend/src/main.tsx`

**Interfaces:**
- Consumes: both money APIs.
- Produces: two-panel conversion, direction switching, copy feedback, inline validation, and validated-value preservation.

- [x] **Step 1: Write failing UI tests**

```tsx
it('converts, copies, and preserves the valid value when direction changes', async () => {
  renderAppAt('/money')
  await user.type(screen.getByLabelText('数字金额'), '-128650.32')
  await user.click(screen.getByRole('button', { name: '转换' }))
  expect(await screen.findByText('负壹拾贰万捌仟陆佰伍拾元叁角贰分')).toBeVisible()
  await user.click(screen.getByRole('button', { name: '复制结果' }))
  expect(screen.getByText('已复制')).toBeVisible()
  await user.click(screen.getByRole('button', { name: '切换为大写转数字' }))
  expect(screen.getByLabelText('人民币大写')).toHaveValue('负壹拾贰万捌仟陆佰伍拾元叁角贰分')
})
```

- [x] **Step 2: Confirm failure, implement the page, and verify desktop/mobile component behavior**

Run: `npm --prefix frontend run test -- --run src/pages/MoneyPage.test.tsx`

Expected after implementation: PASS.

- [x] **Step 3: Record the intended commit**

`feat(money): add responsive conversion workspace`

---

### Task 10: Tax calendar, dual detail views, and tool-local settings

**Files:**
- Create: `frontend/src/pages/CalendarPage.tsx`
- Create: `frontend/src/pages/CalendarPage.test.tsx`
- Create: `frontend/src/components/MonthCalendar.tsx`
- Create: `frontend/src/components/CalendarDetails.tsx`
- Create: `frontend/src/components/TaxToolSettings.tsx`
- Create: `frontend/src/components/SyncStatus.tsx`
- Modify: `frontend/src/main.tsx`

**Interfaces:**
- Consumes: region, calendar, manual sync, tax settings, and test-email APIs.
- Produces: seven-column month grid, region/month selection, official/personalized switch, stale/failure status, source link, unchanged official rows, unknown-item warnings, and embedded tax settings.

- [x] **Step 1: Write failing tests for official immutability and unknown personalized items**

```tsx
it('shows official bssz verbatim and unknown personalized items for confirmation', async () => {
  renderAppAt('/calendar')
  expect(await screen.findByText(officialFixture.bssz)).toBeVisible()
  await user.click(screen.getByRole('tab', { name: '我的税务清单' }))
  expect(screen.getByText('其他待确认')).toBeVisible()
  expect(screen.getByText(unknownFixture.bssz)).toBeVisible()
})
```

- [x] **Step 2: Write failing tests for settings rollback, manual sync status, and disabled test email**

Run: `npm --prefix frontend run test -- --run src/pages/CalendarPage.test.tsx`

Expected before implementation: FAIL.

- [x] **Step 3: Implement calendar and settings components without reconstructing official text**

```tsx
{mode === 'official'
  ? calendar.official_events.map((event) => <OfficialEvent key={event.source_event_id} event={event} />)
  : calendar.personalized_events.map((event) => <PersonalizedEventRow key={event.key} event={event} />)}
```

- [x] **Step 4: Verify the page suite**

Run: `npm --prefix frontend run test -- --run src/pages/CalendarPage.test.tsx`

Expected: PASS.

- [x] **Step 5: Record the intended commit**

`feat(calendar): add dual-view tax calendar workspace`

---

### Task 11: Production container, static hosting, and operational documentation

**Files:**
- Create: `.dockerignore`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `docker/entrypoint.sh`
- Create: `docs/operations.md`
- Modify: `backend/app/main.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: one non-root, single-worker image; migration-before-start; `/data` persistence; SPA fallback that never shadows `/api`.

- [ ] **Step 1: Add a smoke script and build the image**

Run: `docker compose build`

Expected: frontend production assets and Python dependencies build successfully.

- [ ] **Step 2: Start with a fresh named volume and verify migration, health, login, and persistence**

Run: `docker compose up -d`

Run: `docker compose exec app python -m alembic -c backend/alembic.ini current`

Expected: revision `20260721_0001`.

Run: `docker compose exec app ps -o user,pid,args`

Expected: one non-root Uvicorn worker.

- [ ] **Step 3: Restart and verify persisted settings and cache**

Run: `docker compose restart app`

Expected: health returns `ok`; stored tax settings and cached calendar rows remain.

- [ ] **Step 4: Record the intended commit**

`build: add single-container production deployment`

---

### Task 12: Full automated acceptance suite and release gate

**Files:**
- Create: `frontend/playwright.config.ts`
- Create: `frontend/e2e/critical-flows.spec.ts`
- Create: `backend/tests/test_acceptance_contracts.py`
- Modify: `README.md`

**Interfaces:**
- Produces: repeatable verification for all seven approved acceptance scenarios.

- [x] **Step 1: Add API acceptance assertions for the canonical amount and official-text invariant**

```python
def test_canonical_amount_acceptance(authenticated_client):
    encoded = authenticated_client.post("/api/money/to-uppercase", json={"amount": "-128650.32"}).json()
    assert encoded["uppercase"] == "负壹拾贰万捌仟陆佰伍拾元叁角贰分"
    decoded = authenticated_client.post("/api/money/to-number", json={"uppercase": encoded["uppercase"]}).json()
    assert decoded["amount"] == "-128650.32"
```

- [x] **Step 2: Add Playwright critical flows**

```ts
test('administrator completes core desktop flow', async ({ page }) => {
  await login(page)
  await convertCanonicalAmount(page)
  await inspectOfficialAndPersonalizedCalendar(page)
  await configureTaxProfile(page)
  await verifyTestEmailState(page)
})
```

- [ ] **Step 3: Run all release checks**

Run: `python -m pytest backend/tests`

Run: `ruff check backend`

Run: `npm --prefix frontend run lint`

Run: `npm --prefix frontend run test -- --run`

Run: `npm --prefix frontend run build`

Run: `npm --prefix frontend run e2e`

Run: `docker compose up --build -d`

Expected: every command exits 0 and the container health check is healthy.

- [x] **Step 4: Inspect the working tree for secrets and generated artifacts**

Run: `rg -n "ADMIN_PASSWORD|SESSION_SECRET|SMTP_PASSWORD" -g '!*.example' -g '!docs/**' .`

Expected: only environment variable names and test-only placeholder values; no real secrets.

- [ ] **Step 5: Record the intended commit**

`test: cover finance toolkit v1 acceptance flows`

## Execution Order and Checkpoints

1. Tasks 1-3 form the first deployable vertical slice: backend foundation, secure login, and money APIs.
2. Tasks 4-7 add the tax-calendar and reminder domain while preserving upstream isolation.
3. Tasks 8-10 add the complete responsive user interface.
4. Tasks 11-12 create the production image and release gate.
5. After each checkpoint, run all tests introduced so far before continuing.

## Plan Self-Review

- Spec coverage: product scope, visual rules, runtime, all domain modules, APIs, persistence, security, failure states, scheduling, testing, and Docker acceptance each map to at least one task.
- Placeholder scan: no `TBD`, `TODO`, “implement later,” or unspecified error-handling steps remain.
- Type consistency: `TaxToolSettings`, `YearMonth`, `SourceCalendarEvent`, `CalendarMonthResult`, and API field names are stable across consuming tasks.
- Scope: tasks are ordered as four independently testable checkpoints; no task requires a later task to pass its own tests.
