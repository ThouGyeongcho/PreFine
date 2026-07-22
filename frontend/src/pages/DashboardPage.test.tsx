import { screen } from "@testing-library/react";
import { vi } from "vitest";

import { DashboardPage } from "./DashboardPage";
import { jsonResponse, renderWithProviders } from "../test/render";

it("prompts for tax settings when the profile is incomplete", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      jsonResponse({
        default_mode: "official",
        taxpayer_type: null,
        selected_item_codes: [],
        default_region_code: null,
        reminder_days: [7, 3, 1],
        profile_complete: false,
        email_configured: false,
      }),
    ),
  );

  renderWithProviders(<DashboardPage />);

  expect(
    await screen.findByText("完成税务工具设置后启用个性化摘要"),
  ).toBeVisible();
  expect(screen.getByRole("heading", { name: "金额转换" })).toBeVisible();
});

it("shows a personalized calendar summary for a complete profile", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/tools/tax/settings") {
        return jsonResponse({
          default_mode: "personalized",
          taxpayer_type: "general_taxpayer",
          selected_item_codes: ["vat"],
          default_region_code: "111000000",
          reminder_days: [7, 3, 1],
          profile_complete: true,
          email_configured: true,
        });
      }
      if (url.startsWith("/api/calendar?")) {
        return jsonResponse({
          personalized_events: [
            {
              key: "event:vat",
              display_name: "增值税",
              matched_text: "申报缴纳增值税",
              end_date: "2026-07-31",
              needs_confirmation: false,
            },
            {
              key: "event:unknown",
              display_name: "其他待确认",
              matched_text: "神秘新税种",
              end_date: "2026-07-31",
              needs_confirmation: true,
            },
          ],
        });
      }
      throw new Error(`Unexpected API request: ${url}`);
    }),
  );

  renderWithProviders(<DashboardPage />);

  expect(await screen.findByText("近期税务摘要")).toBeVisible();
  expect(await screen.findByText("增值税")).toBeVisible();
  expect(screen.getByText("其他待确认")).toBeVisible();
  expect(
    screen.queryByText("完成税务工具设置后启用个性化摘要"),
  ).not.toBeInTheDocument();
});
