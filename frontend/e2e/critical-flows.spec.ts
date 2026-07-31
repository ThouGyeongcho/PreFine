import { expect, type Locator, type Page, test } from "@playwright/test";

const settings = {
  default_mode: "official",
  taxpayer_type: "general_taxpayer",
  selected_item_codes: ["vat"],
  default_region_code: "111000000",
  reminder_days: [7, 3, 1],
  profile_complete: true,
  email_configured: false,
};

const calendar = {
  region_code: "111000000",
  month: "2026-07",
  official_events: [
    {
      source_event_id: "e2e-event",
      start_date: "2026-07-01",
      end_date: "2026-07-15",
      bssz: "申报缴纳增值税、神秘新税种",
      split_items: ["申报缴纳增值税", "神秘新税种"],
      source_agency: "国家税务总局",
      source_created_at: "2025-12-29 13:40:56",
      source_order: 0,
    },
  ],
  personalized_events: [
    {
      key: "e2e-event:0:vat",
      source_event_id: "e2e-event",
      category: "tax",
      item_code: "vat",
      display_name: "增值税",
      official_text: "申报缴纳增值税、神秘新税种",
      matched_text: "申报缴纳增值税",
      start_date: "2026-07-01",
      end_date: "2026-07-15",
      source_order: 0,
      needs_confirmation: false,
    },
    {
      key: "e2e-event:1:unknown",
      source_event_id: "e2e-event",
      category: "其他待确认",
      item_code: null,
      display_name: "其他待确认",
      official_text: "申报缴纳增值税、神秘新税种",
      matched_text: "神秘新税种",
      start_date: "2026-07-01",
      end_date: "2026-07-15",
      source_order: 0,
      needs_confirmation: true,
    },
  ],
  profile_complete: true,
  stale: true,
  sync_status: "failed_using_cache",
  last_succeeded_at: "2026-07-21T01:00:00Z",
  source_url:
    "https://12366.chinatax.gov.cn/wap/pages/taxcalendar/tax-calendar.html",
};

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("管理员账号").fill("admin");
  await page.getByLabel("密码").fill("e2e-password-not-a-secret");
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page.getByRole("heading", { name: "工作台" })).toBeVisible();
}

async function boundingBox(locator: Locator) {
  const box = await locator.boundingBox();
  expect(box).not.toBeNull();
  return box!;
}

async function mockCalendarApis(page: Page) {
  await page.route("**/api/regions", (route) =>
    route.fulfill({
      json: [
        { code: "111000000", name: "北京", region_code: "11000000" },
        { code: "132000000", name: "江苏", region_code: "32000000" },
      ],
    }),
  );
  await page.route("**/api/tools/tax/catalog", (route) =>
    route.fulfill({
      json: [
        {
          code: "vat",
          category: "tax",
          display_name: "增值税",
          taxpayer_scope: ["general_taxpayer", "small_scale_taxpayer"],
        },
      ],
    }),
  );
  await page.route("**/api/tools/tax/settings", async (route) => {
    if (route.request().method() === "PUT") {
      const body = route.request().postDataJSON();
      await route.fulfill({
        json: { ...body, profile_complete: true, email_configured: false },
      });
      return;
    }
    await route.fulfill({ json: settings });
  });
  await page.route("**/api/calendar?*", (route) =>
    route.fulfill({ json: calendar }),
  );
}

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

  const stackBox = await boundingBox(stack);
  const formBox = await boundingBox(form);
  expect(Math.round(stackBox.width)).toBe(360);
  expect(Math.round(formBox.width)).toBe(304);
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

  const stackBox = await boundingBox(page.locator(".login-card-stack"));
  expect(stackBox.x).toBeGreaterThanOrEqual(16);
  expect(stackBox.x + stackBox.width).toBeLessThanOrEqual(304);
});

test("@desktop administrator completes the core desktop flow", async ({
  page,
}) => {
  await login(page);

  await page.getByRole("link", { name: "金额转换", exact: true }).click();
  await expect(page.locator(".sidebar-brand img")).toHaveAttribute(
    "src",
    "/prefine-logo-on-dark-512.png",
  );
  await expect(page.locator(".brand-mark-small")).toHaveCSS("width", "47px");
  await expect(
    page.getByText(
      "转换人民币数字与规范大写，并提供便于核对和使用的金额写法。",
    ),
  ).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "便捷写法" })).toHaveCount(0);

  await page.getByLabel("数字金额").fill("-128650.32");
  await page.getByRole("button", { name: "转换", exact: true }).click();
  await expect(
    page.getByLabel("转换结果").locator('[aria-hidden="true"]'),
  ).toHaveText("负壹拾贰万捌仟陆佰伍拾元叁角贰分");
  await expect(page.getByRole("group", { name: "快速读数" })).toContainText(
    "-12万8650.32",
  );

  const panelsBox = await boundingBox(page.locator(".money-panels"));
  const convertBox = await boundingBox(page.locator(".money-convert"));
  const formatsBox = await boundingBox(page.locator(".money-formats"));
  expect(Math.abs(panelsBox.width - convertBox.width)).toBeLessThanOrEqual(1);
  expect(Math.abs(panelsBox.width - formatsBox.width)).toBeLessThanOrEqual(1);

  const panels = page.locator(".money-panel");
  const leftPanel = await boundingBox(panels.nth(0));
  const rightPanel = await boundingBox(panels.nth(1));
  expect(Math.abs(leftPanel.width - rightPanel.width)).toBeLessThanOrEqual(1);
  expect(Math.abs(leftPanel.height - rightPanel.height)).toBeLessThanOrEqual(1);

  const contentBoxes = page.locator(".money-panel .money-content-box");
  const leftContent = await boundingBox(contentBoxes.nth(0));
  const rightContent = await boundingBox(contentBoxes.nth(1));
  expect(Math.abs(leftContent.width - rightContent.width)).toBeLessThanOrEqual(
    1,
  );
  expect(
    Math.abs(leftContent.height - rightContent.height),
  ).toBeLessThanOrEqual(1);

  const panelCopies = page.locator(".money-panel .money-copy");
  const leftCopy = await boundingBox(panelCopies.nth(0));
  const rightCopy = await boundingBox(panelCopies.nth(1));
  expect(Math.abs(leftCopy.width - rightCopy.width)).toBeLessThanOrEqual(1);
  expect(Math.abs(leftCopy.height - rightCopy.height)).toBeLessThanOrEqual(1);
  expect(leftCopy.y).toBeGreaterThan(leftContent.y + leftContent.height);
  expect(rightCopy.y).toBeGreaterThan(rightContent.y + rightContent.height);

  await page.getByRole("button", { name: "大写转数字" }).click();
  await page.getByLabel("人民币大写").fill("肆圆整");
  await page.getByRole("button", { name: "转换", exact: true }).click();
  await expect(page.getByLabel("人民币大写")).toHaveValue("肆元整");
  await expect(page.getByText("原输入：肆圆整 · 已规范")).toBeVisible();
  await expect(page.getByRole("status", { name: "转换结果" })).toHaveText(
    "4.00",
  );
  await page.getByRole("button", { name: "复制英文金额" }).click();
  await expect(page.getByRole("button", { name: "复制英文金额" })).toHaveText(
    "已复制",
  );
  await expect(page.locator(".copy-status")).toHaveCount(0);

  await mockCalendarApis(page);
  await page.getByRole("link", { name: "税收日历" }).click();
  await expect(page.getByText("申报缴纳增值税、神秘新税种")).toBeVisible();
  await expect(page.getByText("同步失败，正在显示上次数据")).toBeVisible();
  await page.getByRole("tab", { name: "我的税务清单" }).click();
  await expect(page.getByText("其他待确认")).toBeVisible();
  await expect(page.getByText("神秘新税种", { exact: true })).toBeVisible();

  const taxSettings = page.getByRole("region", { name: "税务工具设置" });
  await taxSettings.getByLabel("默认地区").selectOption("132000000");
  await taxSettings.getByRole("button", { name: "保存税务设置" }).click();
  await expect(taxSettings.getByText("设置已保存")).toBeVisible();
  await expect(
    taxSettings.getByRole("button", { name: "发送测试邮件" }),
  ).toBeDisabled();
});

test("@mobile money layout is single-column at 320px without overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await login(page);
  await page.getByRole("button", { name: "打开导航" }).click();
  await page.getByRole("link", { name: "金额转换", exact: true }).click();
  await page.getByLabel("数字金额").fill("4.00");
  await page.getByRole("button", { name: "转换", exact: true }).click();

  const pageOverflows = await page.evaluate(
    () =>
      document.documentElement.scrollWidth >
      document.documentElement.clientWidth,
  );
  expect(pageOverflows).toBe(false);
  expect(
    await page
      .locator(".money-panels")
      .evaluate((element) => getComputedStyle(element).gridTemplateColumns),
  ).not.toContain(" ");
  expect(
    await page
      .locator(".money-formats")
      .evaluate((element) => getComputedStyle(element).gridTemplateColumns),
  ).not.toContain(" ");

  const copyButtons = page.locator(".money-copy");
  await expect(copyButtons).toHaveCount(5);
  for (let index = 0; index < 5; index += 1) {
    await expect(copyButtons.nth(index)).toBeEnabled();
  }
  await expect(page.locator(".money-convert")).toBeEnabled();
});

test("@mobile mobile layout keeps core actions reachable without page overflow", async ({
  page,
}) => {
  await mockCalendarApis(page);
  await login(page);
  await page.getByRole("button", { name: "打开导航" }).click();
  await page.getByRole("link", { name: "税收日历", exact: true }).click();
  await expect(page.getByRole("tab", { name: "官方税历" })).toBeVisible();
  await page.getByRole("tab", { name: "我的税务清单" }).click();
  await expect(page.getByText("其他待确认")).toBeVisible();
  await expect(
    page.getByRole("region", { name: "税务工具设置" }),
  ).toBeVisible();

  const pageOverflows = await page.evaluate(
    () =>
      document.documentElement.scrollWidth >
      document.documentElement.clientWidth,
  );
  expect(pageOverflows).toBe(false);
});

test("@desktop logout prevents browser back from restoring private data", async ({
  page,
}) => {
  await mockCalendarApis(page);
  await login(page);
  await page.getByRole("link", { name: "税收日历", exact: true }).click();
  await expect(page.getByRole("heading", { name: "税收日历" })).toBeVisible();
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: "登录" }),
  ).toBeVisible();

  await page.goBack();

  await expect(
    page.getByRole("heading", { level: 1, name: "登录" }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "税收日历" })).toHaveCount(0);
});
