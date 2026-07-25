# PreFine Login Page Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current login page with the approved PreFine design, verify it at desktop and 320px widths, and publish the implementation to GitHub without building or publishing a Docker image.

**Architecture:** Keep authentication state and API flow inside the existing `LoginPage` component. Restructure only its semantic markup, isolate all new presentation under `login-*` classes, and verify responsive geometry with Playwright while preserving the existing API contract and redirect behavior.

**Tech Stack:** React 19, TypeScript 5.9, TanStack Query, Vitest, React Testing Library, CSS, Playwright.

## Global Constraints

- Work on branch `codex/login-page-refresh`; do not push implementation commits directly to `main`.
- The approved design spec is `docs/superpowers/specs/2026-07-26-prefine-login-page-refresh-design.md`.
- Keep `POST /api/auth/login`, request fields `username` and `password`, and the successful redirect unchanged.
- Reuse `/prefine-logo-512.png`; add no image or font dependency.
- Desktop card width is `360px`; desktop form width is `304px`.
- The blue layer is `20px` high with `10px` visible above the white card.
- Brand sizes remain `74px / 42px / 15px` for mark, wordmark, and “登录”.
- The page must not overflow horizontally at a `320px` viewport.
- Add no registration, password recovery, remember-login, version footer, background decoration, or helper copy.
- Do not run `docker build`, `docker compose build`, image tagging, or image publishing commands.
- After all verification passes, push the feature branch and open a draft pull request on GitHub.

---

### Task 1: Replace the login page semantic structure

**Files:**
- Modify: `frontend/src/pages/LoginPage.test.tsx:10-75`
- Modify: `frontend/src/pages/LoginPage.tsx:38-78`

**Interfaces:**
- Consumes: existing `apiRequest<void>("/api/auth/login", ...)`, `username`, `password`, `login.isPending`, and `errorMessage`.
- Produces: stable classes `login-card-stack`, `login-blue-layer`, `login-card`, `login-identity`, `login-brand-mark`, `login-title`, `login-form`, `login-field`, and `login-submit` for Task 2.

- [ ] **Step 1: Update the component tests to describe the approved content**

Replace the first test and update the login field queries in the remaining tests:

```tsx
it("renders the approved PreFine login structure without duplicate copy", () => {
  renderWithProviders(<LoginPage />, "/login");

  const mark = document.querySelector<HTMLImageElement>(".login-brand-mark");
  expect(mark).toHaveAttribute("src", "/prefine-logo-512.png");
  expect(mark).toHaveAttribute("alt", "");
  expect(screen.getByText("PreFine")).toBeVisible();
  expect(
    screen.getByRole("heading", { level: 1, name: "登录" }),
  ).toBeVisible();
  expect(screen.getByLabelText("管理员账号")).toHaveAttribute(
    "autocomplete",
    "username",
  );
  expect(screen.getByLabelText("密码")).toHaveAttribute(
    "autocomplete",
    "current-password",
  );
  expect(screen.queryByText("管理员登录")).not.toBeInTheDocument();
  expect(
    screen.queryByText("使用部署时配置的管理员账号继续。"),
  ).not.toBeInTheDocument();
});
```

In the success and error tests, replace:

```tsx
screen.getByLabelText("用户名")
```

with:

```tsx
screen.getByLabelText("管理员账号")
```

Add a focused pending-state test:

```tsx
it("disables the action while login is pending", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => new Promise<Response>(() => undefined)),
  );
  const user = userEvent.setup();
  renderWithProviders(<LoginPage />, "/login");

  await user.type(screen.getByLabelText("管理员账号"), "admin");
  await user.type(screen.getByLabelText("密码"), "secret");
  await user.click(screen.getByRole("button", { name: "登录" }));

  expect(
    screen.getByRole("button", { name: "正在登录…" }),
  ).toBeDisabled();
});
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
npm --prefix frontend run test -- --run src/pages/LoginPage.test.tsx
```

Expected: FAIL because the current page still exposes the “管理员登录” heading, “用户名” label, helper copy, and non-decorative logo alt text.

- [ ] **Step 3: Replace only the `LoginPage` return markup**

Keep all hooks and request logic unchanged. Replace the current return block with:

```tsx
return (
  <main className="login-page">
    <div className="login-card-stack">
      <div className="login-blue-layer" aria-hidden="true" />
      <section className="login-card" aria-labelledby="login-title">
        <div className="login-identity">
          <img
            className="brand-mark login-brand-mark"
            src="/prefine-logo-512.png"
            alt=""
          />
          <p className="login-brand-name">PreFine</p>
        </div>
        <h1 id="login-title" className="login-title">
          登录
        </h1>
        <form onSubmit={handleSubmit} className="login-form">
          <label className="login-field">
            管理员账号
            <input
              name="username"
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
            />
          </label>
          <label className="login-field">
            密码
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          {errorMessage ? (
            <div role="alert" className="inline-error">
              {errorMessage}
            </div>
          ) : null}
          <button
            className="button login-submit"
            type="submit"
            disabled={login.isPending}
          >
            {login.isPending ? "正在登录…" : "登录"}
          </button>
        </form>
      </section>
    </div>
  </main>
);
```

- [ ] **Step 4: Run the focused test and verify GREEN**

Run:

```powershell
npm --prefix frontend run test -- --run src/pages/LoginPage.test.tsx
```

Expected: all `LoginPage.test.tsx` tests PASS, including login redirect and error preservation.

- [ ] **Step 5: Commit the semantic refresh**

```powershell
git add frontend/src/pages/LoginPage.tsx frontend/src/pages/LoginPage.test.tsx
git commit -m "feat(ui): refresh login page structure"
```

---

### Task 2: Implement the approved visual geometry and responsive contract

**Files:**
- Modify: `frontend/e2e/critical-flows.spec.ts:30-36`
- Modify: `frontend/e2e/critical-flows.spec.ts:130-178`
- Modify: `frontend/src/styles.css:105-171`
- Modify: `frontend/src/styles.css:858-861`

**Interfaces:**
- Consumes: the `login-*` class names produced in Task 1.
- Produces: a `360px` maximum-width layered card, `304px` form, approved C2 typography, C-style inputs/button, and responsive behavior down to `320px`.

- [ ] **Step 1: Update existing E2E selectors**

In `login(page)`, replace:

```ts
await page.getByLabel("用户名").fill("admin");
```

with:

```ts
await page.getByLabel("管理员账号").fill("admin");
```

In the logout test, replace both heading assertions:

```ts
await expect(page.getByRole("heading", { name: "管理员登录" })).toBeVisible();
```

with:

```ts
await expect(
  page.getByRole("heading", { level: 1, name: "登录" }),
).toBeVisible();
```

- [ ] **Step 2: Add desktop and 320px visual-contract tests**

Add these tests before the existing desktop core-flow test:

```ts
test("@desktop login page uses the approved layered geometry", async ({
  page,
}) => {
  await page.goto("/login");

  const stack = page.locator(".login-card-stack");
  const layer = page.locator(".login-blue-layer");
  const card = page.locator(".login-card");
  const form = page.locator(".login-form");

  await expect(stack).toBeVisible();
  await expect(layer).toHaveCSS("height", "20px");
  await expect(card).toHaveCSS("border-top-width", "0px");
  await expect(card).toHaveCSS("border-top-left-radius", "0px");
  await expect(card).toHaveCSS("border-top-right-radius", "0px");
  await expect(page.locator(".login-brand-mark")).toHaveCSS("width", "74px");
  await expect(page.locator(".login-brand-name")).toHaveCSS(
    "font-size",
    "42px",
  );
  await expect(page.locator(".login-title")).toHaveCSS("font-size", "15px");

  const stackBox = await stack.boundingBox();
  const formBox = await form.boundingBox();
  expect(Math.round(stackBox?.width ?? 0)).toBe(360);
  expect(Math.round(formBox?.width ?? 0)).toBe(304);
});

test("@mobile login page remains usable at 320px without overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto("/login");

  await expect(page.getByLabel("管理员账号")).toBeVisible();
  await expect(page.getByLabel("密码")).toBeVisible();
  await expect(page.getByRole("button", { name: "登录" })).toBeVisible();

  const pageOverflows = await page.evaluate(
    () =>
      document.documentElement.scrollWidth >
      document.documentElement.clientWidth,
  );
  expect(pageOverflows).toBe(false);

  const stackBox = await page.locator(".login-card-stack").boundingBox();
  expect(stackBox?.x ?? -1).toBeGreaterThanOrEqual(16);
  expect((stackBox?.x ?? 0) + (stackBox?.width ?? 0)).toBeLessThanOrEqual(304);
});
```

- [ ] **Step 3: Run the focused E2E tests and verify RED**

Run:

```powershell
npm --prefix frontend run e2e -- --grep "approved layered geometry|320px"
```

Expected: FAIL because the approved layered geometry and responsive classes have not been styled.

- [ ] **Step 4: Replace the login-specific CSS**

Keep `.brand-mark` and `.brand-mark-small` because `AppShell` also uses them. Replace the login page/card/form rules from `.login-page` through `.form-stack label` with:

```css
.login-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 16px;
  background: #fff;
}
.login-card-stack {
  position: relative;
  width: min(360px, 100%);
  padding-top: 10px;
}
.login-blue-layer {
  position: absolute;
  inset: 0 0 auto;
  height: 20px;
  border-radius: 14px 14px 8px 8px;
  background: var(--accent);
}
.login-card {
  position: relative;
  border: 1px solid var(--divider);
  border-top: 0;
  border-radius: 0 0 12px 12px;
  padding: 36px 27px 39px;
  background: #fff;
}
.brand-mark {
  display: block;
  width: 64px;
  height: 64px;
  margin-bottom: 16px;
  object-fit: contain;
}
.brand-mark-small {
  width: 32px;
  height: 32px;
  margin: 0;
}
.login-identity {
  display: grid;
  justify-items: center;
}
.login-brand-mark {
  width: 74px;
  height: 74px;
  margin: 0;
}
.login-brand-name {
  margin: 13px 0 0;
  color: var(--ink);
  font-size: 42px;
  font-weight: 500;
  letter-spacing: 0.11em;
  line-height: 1.1;
}
.login-title {
  margin: 23px 0 31px;
  color: var(--muted);
  text-align: center;
  text-indent: 0.24em;
  font-size: 15px;
  font-weight: 400;
  letter-spacing: 0.24em;
}
.login-form {
  display: grid;
  width: min(304px, 100%);
  margin: 0 auto;
}
.login-field {
  display: grid;
  gap: 7px;
  color: var(--body);
  font-size: 12px;
}
.login-field + .login-field {
  margin-top: 16px;
}
.login-field input {
  height: 43px;
  min-height: 43px;
  border-color: var(--divider);
  border-radius: 10px;
}
.login-form .inline-error {
  margin-top: 16px;
}
.login-submit {
  width: 100%;
  height: 43px;
  margin-top: 22px;
  border-radius: 10px;
  background: var(--ink);
  color: #fff;
}
.login-submit:hover:not(:disabled) {
  background: #2d3036;
}
.login-submit:disabled {
  background: var(--divider-strong);
  color: #fff;
}
```

Replace the existing mobile `.login-card` rule with:

```css
@media (max-width: 400px) {
  .login-card {
    padding: 32px 20px 34px;
  }
}
```

- [ ] **Step 5: Run the focused E2E tests and verify GREEN**

Run:

```powershell
npm --prefix frontend run e2e -- --grep "approved layered geometry|320px"
```

Expected: both focused tests PASS in their matching desktop/mobile projects.

- [ ] **Step 6: Run the login component tests again**

Run:

```powershell
npm --prefix frontend run test -- --run src/pages/LoginPage.test.tsx
```

Expected: all login component tests PASS.

- [ ] **Step 7: Commit the visual implementation**

```powershell
git add frontend/src/styles.css frontend/e2e/critical-flows.spec.ts
git commit -m "style(ui): apply approved login page design"
```

---

### Task 3: Verify and publish the implementation

**Files:**
- Verify only; no new production files.

**Interfaces:**
- Consumes: the complete implementation from Tasks 1 and 2.
- Produces: a pushed `codex/login-page-refresh` branch and a draft pull request for user review.

- [ ] **Step 1: Run all frontend unit tests**

```powershell
npm --prefix frontend run test -- --run
```

Expected: Vitest exits `0` with no failed tests.

- [ ] **Step 2: Run lint and formatting checks**

```powershell
npm --prefix frontend run lint
```

Expected: ESLint and Prettier exit `0` with no warnings or formatting failures.

- [ ] **Step 3: Run a production frontend build**

```powershell
npm --prefix frontend run build
```

Expected: TypeScript and Vite exit `0`, producing `frontend/dist`.

- [ ] **Step 4: Run the full Playwright acceptance suite**

```powershell
npm --prefix frontend run e2e
```

Expected: all desktop and mobile acceptance tests PASS, including login, logout, conversion, calendar, and no-overflow checks.

- [ ] **Step 5: Inspect the final diff and working tree**

```powershell
git diff main...HEAD --check
git diff main...HEAD --stat
git status --short
```

Expected: no whitespace errors; only the approved spec, plan, login component/tests, login CSS, and E2E flow are changed; the working tree is clean.

- [ ] **Step 6: Publish without Docker packaging**

Use the `github:yeet` skill to:

1. Confirm the branch is `codex/login-page-refresh`.
2. Push the branch to `origin`.
3. Open a draft pull request titled `feat(ui): refresh PreFine login page`.
4. Include the unit, lint, build, and E2E results in the pull request body.
5. State explicitly: `Docker image not built or published; packaging deferred until the frontend is fully approved.`

Do not run any Docker command in this task.
