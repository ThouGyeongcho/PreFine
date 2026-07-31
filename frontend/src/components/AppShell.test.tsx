import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { vi } from "vitest";

import { AppShell } from "./AppShell";
import { renderWithProviders } from "../test/render";

it("shows the four approved primary navigation destinations", () => {
  renderWithProviders(
    <AppShell>
      <h1>当前页面</h1>
    </AppShell>,
  );

  expect(screen.getByRole("link", { name: "工作台" })).toHaveAttribute(
    "href",
    "/",
  );
  expect(screen.getByRole("link", { name: "金额转换" })).toHaveAttribute(
    "href",
    "/money",
  );
  expect(screen.getByRole("link", { name: "税收日历" })).toHaveAttribute(
    "href",
    "/calendar",
  );
  expect(screen.getByRole("link", { name: "系统设置" })).toHaveAttribute(
    "href",
    "/system",
  );
  expect(screen.getByRole("heading", { name: "当前页面" })).toBeVisible();
  expect(screen.getAllByText("PreFine")).toHaveLength(2);
  expect(document.querySelector(".sidebar-brand img")).toHaveAttribute(
    "src",
    "/prefine-logo-on-dark-512.png",
  );
});

it("clears authenticated queries after logout", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response(null, { status: 204 })),
  );
  const user = userEvent.setup();
  const { queryClient } = renderWithProviders(
    <Routes>
      <Route
        path="/private"
        element={
          <AppShell>
            <h1>私密数据</h1>
          </AppShell>
        }
      />
      <Route path="/login" element={<h1>登录 PreFine</h1>} />
    </Routes>,
    "/private",
  );
  queryClient.setQueryData(["tax-settings"], { reminder_days: [7, 3, 1] });

  await user.click(screen.getByRole("button", { name: "退出登录" }));

  expect(
    await screen.findByRole("heading", { name: "登录 PreFine" }),
  ).toBeVisible();
  expect(queryClient.getQueryData(["tax-settings"])).toBeUndefined();
});
