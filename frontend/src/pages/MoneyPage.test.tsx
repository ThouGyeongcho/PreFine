import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { MoneyPage } from "./MoneyPage";
import { jsonResponse, renderWithProviders } from "../test/render";

it("converts, copies, and preserves the validated value when direction changes", async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    jsonResponse({
      amount: "-128650.32",
      uppercase: "负壹拾贰万捌仟陆佰伍拾元叁角贰分",
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  const user = userEvent.setup();
  renderWithProviders(<MoneyPage />);

  await user.type(screen.getByLabelText("数字金额"), "-128650.32");
  await user.click(screen.getByRole("button", { name: "转换" }));

  expect(
    await screen.findByText("负壹拾贰万捌仟陆佰伍拾元叁角贰分"),
  ).toBeVisible();
  await user.click(screen.getByRole("button", { name: "复制结果" }));
  expect(await navigator.clipboard.readText()).toBe(
    "负壹拾贰万捌仟陆佰伍拾元叁角贰分",
  );
  expect(screen.getByText("已复制")).toBeVisible();

  await user.click(screen.getByRole("button", { name: "切换为大写转数字" }));
  expect(screen.getByLabelText("人民币大写")).toHaveValue(
    "负壹拾贰万捌仟陆佰伍拾元叁角贰分",
  );
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/money/to-uppercase",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ amount: "-128650.32" }),
    }),
  );
});

it("keeps invalid input visible and shows the API error inline", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      jsonResponse(
        {
          code: "invalid_money_format",
          message: "请输入规范数字，最多保留两位小数",
          details: {},
        },
        422,
      ),
    ),
  );
  const user = userEvent.setup();
  renderWithProviders(<MoneyPage />);

  await user.type(screen.getByLabelText("数字金额"), "1.001");
  await user.click(screen.getByRole("button", { name: "转换" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "请输入规范数字，最多保留两位小数",
  );
  expect(screen.getByLabelText("数字金额")).toHaveValue("1.001");
  expect(
    screen.queryByRole("status", { name: "转换结果" }),
  ).not.toBeInTheDocument();
});

it("converts canonical uppercase back to its normalized number", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(jsonResponse({ amount: "-128650.32" })),
  );
  const user = userEvent.setup();
  renderWithProviders(<MoneyPage />);

  await user.click(screen.getByRole("button", { name: "切换为大写转数字" }));
  await user.type(
    screen.getByLabelText("人民币大写"),
    "负壹拾贰万捌仟陆佰伍拾元叁角贰分",
  );
  await user.click(screen.getByRole("button", { name: "转换" }));

  expect(await screen.findByText("-128650.32")).toBeVisible();
});
