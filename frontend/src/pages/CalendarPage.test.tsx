import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { CalendarPage } from "./CalendarPage";
import type { TaxToolSettings } from "../api/types";
import { jsonResponse, renderWithProviders } from "../test/render";

const regions = [
  { code: "111000000", name: "北京", region_code: "11000000" },
  { code: "132000000", name: "江苏", region_code: "32000000" },
];

const catalog = [
  {
    code: "vat",
    category: "tax",
    display_name: "增值税",
    taxpayer_scope: ["general_taxpayer", "small_scale_taxpayer"],
  },
  {
    code: "corporate_income_tax",
    category: "tax",
    display_name: "企业所得税",
    taxpayer_scope: ["general_taxpayer", "small_scale_taxpayer"],
  },
];

const configuredSettings: TaxToolSettings = {
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
      source_event_id: "event-1",
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
      key: "event-1:0:vat",
      source_event_id: "event-1",
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
      key: "event-1:1:unknown",
      source_event_id: "event-1",
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
  stale: false,
  sync_status: "fresh",
  last_succeeded_at: "2026-07-21T01:00:00Z",
  source_url:
    "https://12366.chinatax.gov.cn/wap/pages/taxcalendar/tax-calendar.html",
};

function mockApi(
  options: { settings?: typeof configuredSettings; putFails?: boolean } = {},
) {
  const settings = options.settings ?? configuredSettings;
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/regions") return jsonResponse(regions);
    if (url === "/api/tools/tax/catalog") return jsonResponse(catalog);
    if (url === "/api/tools/tax/settings" && init?.method === "PUT") {
      if (options.putFails) {
        return jsonResponse(
          { code: "save_failed", message: "保存失败", details: {} },
          500,
        );
      }
      const body = JSON.parse(String(init?.body));
      return jsonResponse({
        ...body,
        profile_complete: true,
        email_configured: false,
      });
    }
    if (url === "/api/tools/tax/settings") return jsonResponse(settings);
    if (url.startsWith("/api/calendar?")) return jsonResponse(calendar);
    if (url === "/api/tools/tax/sync") return jsonResponse(calendar);
    throw new Error(`Unexpected API request: ${url}`);
  });
}

it("shows official bssz verbatim and unknown personalized items for confirmation", async () => {
  vi.stubGlobal("fetch", mockApi());
  const user = userEvent.setup();
  renderWithProviders(<CalendarPage />);

  expect(await screen.findByText("申报缴纳增值税、神秘新税种")).toBeVisible();
  expect(screen.getByRole("link", { name: "查看 12366 来源" })).toHaveAttribute(
    "href",
    calendar.source_url,
  );

  await user.click(screen.getByRole("tab", { name: "我的税务清单" }));
  expect(screen.getByText("其他待确认")).toBeVisible();
  expect(screen.getByText("神秘新税种")).toBeVisible();
  expect(screen.getByText("申报缴纳增值税、神秘新税种")).toBeVisible();
  expect(screen.getByText("2026-07-01 — 2026-07-15")).toBeVisible();
  expect(screen.getAllByText("增值税")[0]).toBeVisible();
});

it("saves tool-local profile settings and disables test email when SMTP is absent", async () => {
  const incomplete = {
    ...configuredSettings,
    taxpayer_type: null,
    selected_item_codes: [],
    profile_complete: false,
  };
  const fetchMock = mockApi({
    settings: incomplete as typeof configuredSettings,
  });
  vi.stubGlobal("fetch", fetchMock);
  const user = userEvent.setup();
  renderWithProviders(<CalendarPage />);

  const settingsPanel = await screen.findByRole("region", {
    name: "税务工具设置",
  });
  await user.selectOptions(
    within(settingsPanel).getByLabelText("纳税人身份"),
    "general_taxpayer",
  );
  await user.click(
    within(settingsPanel).getByRole("checkbox", { name: "增值税" }),
  );
  await user.click(
    within(settingsPanel).getByRole("button", { name: "保存税务设置" }),
  );

  expect(await within(settingsPanel).findByText("设置已保存")).toBeVisible();
  expect(
    within(settingsPanel).getByRole("button", { name: "发送测试邮件" }),
  ).toBeDisabled();
  const putCall = fetchMock.mock.calls.find(
    ([url, init]) =>
      url === "/api/tools/tax/settings" && init?.method === "PUT",
  );
  expect(JSON.parse(String(putCall?.[1]?.body)).selected_item_codes).toEqual([
    "vat",
  ]);
});

it("restores persisted settings when saving fails", async () => {
  vi.stubGlobal("fetch", mockApi({ putFails: true }));
  const user = userEvent.setup();
  renderWithProviders(<CalendarPage />);

  const settingsPanel = await screen.findByRole("region", {
    name: "税务工具设置",
  });
  const identity = within(settingsPanel).getByLabelText("纳税人身份");
  expect(identity).toHaveValue("general_taxpayer");
  await user.selectOptions(identity, "small_scale_taxpayer");
  await user.click(
    within(settingsPanel).getByRole("button", { name: "保存税务设置" }),
  );

  expect(await within(settingsPanel).findByRole("alert")).toHaveTextContent(
    "保存失败",
  );
  expect(identity).toHaveValue("general_taxpayer");
});
