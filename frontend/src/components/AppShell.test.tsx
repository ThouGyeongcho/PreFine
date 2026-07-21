import { screen } from "@testing-library/react";

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
  expect(screen.getByRole("link", { name: "金额大小写转换" })).toHaveAttribute(
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
});
