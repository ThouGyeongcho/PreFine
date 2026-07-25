import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { vi } from "vitest";

import { LoginPage } from "./LoginPage";
import { SessionBoundary } from "../components/SessionBoundary";
import { jsonResponse, renderWithProviders } from "../test/render";

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

it("logs in and redirects to the dashboard", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValue(new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", fetchMock);
  const user = userEvent.setup();
  renderWithProviders(
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<h1>工作台</h1>} />
    </Routes>,
    "/login",
  );

  await user.type(screen.getByLabelText("管理员账号"), "admin");
  await user.type(screen.getByLabelText("密码"), "secret");
  await user.click(screen.getByRole("button", { name: "登录" }));

  expect(await screen.findByRole("heading", { name: "工作台" })).toBeVisible();
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/auth/login",
    expect.objectContaining({ method: "POST", credentials: "same-origin" }),
  );
});

it("shows the server login error without clearing the password", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      jsonResponse(
        {
          code: "invalid_credentials",
          message: "用户名或密码错误",
          details: {},
        },
        401,
      ),
    ),
  );
  const user = userEvent.setup();
  renderWithProviders(
    <SessionBoundary>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
      </Routes>
    </SessionBoundary>,
    "/login",
  );

  await user.type(screen.getByLabelText("管理员账号"), "admin");
  await user.type(screen.getByLabelText("密码"), "wrong");
  await user.click(screen.getByRole("button", { name: "登录" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "用户名或密码错误",
  );
  expect(screen.getByLabelText("密码")).toHaveValue("wrong");
});

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
