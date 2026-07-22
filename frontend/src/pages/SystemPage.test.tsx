import { screen } from "@testing-library/react";
import { vi } from "vitest";

import { SystemPage } from "./SystemPage";
import { jsonResponse, renderWithProviders } from "../test/render";

it("shows whether reminder email is configured without exposing secrets", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      if (String(input) === "/api/health") {
        return jsonResponse({
          status: "ok",
          database: "ok",
          scheduler: "running",
          version: "0.1.1",
        });
      }
      if (String(input) === "/api/tools/tax/settings") {
        return jsonResponse({ email_configured: false });
      }
      throw new Error(`Unexpected API request: ${String(input)}`);
    }),
  );

  renderWithProviders(<SystemPage />);

  expect(await screen.findByText("未配置")).toBeVisible();
  expect(screen.getByText("邮件提醒")).toBeVisible();
  expect(screen.getByText("0.1.1")).toBeVisible();
});
