import { expect, type Page, test } from "@playwright/test";

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
  await page.getByLabel("用户名").fill("admin");
  await page.getByLabel("密码").fill("e2e-password-not-a-secret");
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page.getByRole("heading", { name: "工作台" })).toBeVisible();
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

test("@desktop administrator completes the core desktop flow", async ({
  page,
}) => {
  await login(page);

  await page.getByRole("link", { name: "金额大小写转换" }).click();
  await page.getByLabel("数字金额").fill("-128650.32");
  await page.getByRole("button", { name: "转换" }).click();
  await expect(page.getByLabel("转换结果")).toHaveText(
    "负壹拾贰万捌仟陆佰伍拾元叁角贰分",
  );
  await page.getByRole("button", { name: "切换为大写转数字" }).click();
  await expect(page.getByLabel("人民币大写")).toHaveValue(
    "负壹拾贰万捌仟陆佰伍拾元叁角贰分",
  );
  await page.getByRole("button", { name: "转换" }).click();
  await expect(page.getByLabel("转换结果")).toHaveText("-128650.32");

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
    page.getByRole("heading", { name: "登录 PreFine" }),
  ).toBeVisible();

  await page.goBack();

  await expect(
    page.getByRole("heading", { name: "登录 PreFine" }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "税收日历" })).toHaveCount(0);
});
