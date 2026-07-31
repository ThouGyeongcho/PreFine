import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, vi } from "vitest";

import { MoneyPage } from "./MoneyPage";
import { jsonResponse, renderWithProviders } from "../test/render";

const negativeResponse = {
  amount: "-128650.32",
  uppercase: "负壹拾贰万捌仟陆佰伍拾元叁角贰分",
  grouped: "-128,650.32",
  quick_read: "-12万8650.32",
  english:
    "Negative one hundred twenty-eight thousand six hundred fifty yuan and thirty-two fen only",
  normalization_note: null,
};

const roundResponse = {
  amount: "4.00",
  uppercase: "肆元整",
  grouped: "4",
  quick_read: "4",
  english: "Four yuan only",
  normalization_note: "已按标准写法转换：“圆”应写作“元”。",
};

const originalExecCommand = document.execCommand;

afterEach(() => {
  Object.defineProperty(document, "execCommand", {
    configurable: true,
    value: originalExecCommand,
  });
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it("renders the concise symmetric workbench and submits a number conversion", async () => {
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse(negativeResponse));
  vi.stubGlobal("fetch", fetchMock);
  const user = userEvent.setup();
  renderWithProviders(<MoneyPage />);

  expect(
    screen.getByRole("heading", { name: "金额转换", level: 1 }),
  ).toBeVisible();
  expect(
    screen.queryByText(
      "转换人民币数字与规范大写，并提供便于核对和使用的金额写法。",
    ),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("heading", { name: "便捷写法" }),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "输入金额" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "转换结果" })).toBeVisible();
  expect(screen.getByRole("button", { name: "数字转大写" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(screen.getByRole("button", { name: "大写转数字" })).toHaveAttribute(
    "aria-pressed",
    "false",
  );

  await user.type(screen.getByLabelText("数字金额"), "-128650.32");
  await user.click(screen.getByRole("button", { name: "转换" }));

  expect(
    await screen.findByText("负壹拾贰万捌仟陆佰伍拾元叁角贰分"),
  ).toBeVisible();
  expect(screen.getByText("-128,650.32")).toBeVisible();
  expect(screen.getByText("-12万8650.32")).toHaveClass("visually-hidden");
  expect(screen.getByText(negativeResponse.english)).toBeVisible();
  expect(screen.getAllByRole("button", { name: /^复制/ })).toHaveLength(5);
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/money/to-uppercase",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ amount: "-128650.32" }),
    }),
  );
});

it("keeps copy feedback inside the latest clicked button", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(jsonResponse(negativeResponse)),
  );
  const user = userEvent.setup();
  renderWithProviders(<MoneyPage />);

  await user.type(screen.getByLabelText("数字金额"), "-128650.32");
  await user.click(screen.getByRole("button", { name: "转换" }));

  const primaryCopy = screen.getByRole("button", { name: "复制转换结果" });
  await user.click(primaryCopy);
  expect(primaryCopy).toHaveTextContent("已复制");
  expect(screen.getAllByText("已复制")).toHaveLength(1);
  expect(await navigator.clipboard.readText()).toBe(
    "负壹拾贰万捌仟陆佰伍拾元叁角贰分",
  );

  const englishCopy = screen.getByRole("button", { name: "复制英文金额" });
  await user.click(englishCopy);
  expect(primaryCopy).toHaveTextContent("复制");
  expect(englishCopy).toHaveTextContent("已复制");
  expect(screen.getAllByText("已复制")).toHaveLength(1);
  expect(await navigator.clipboard.readText()).toBe(negativeResponse.english);
});

it("normalizes round to yuan in the input panel and carries the canonical pair", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(jsonResponse(roundResponse)),
  );
  const user = userEvent.setup();
  renderWithProviders(<MoneyPage />);

  await user.click(screen.getByRole("button", { name: "大写转数字" }));
  await user.type(screen.getByLabelText("人民币大写"), "肆圆整");
  await user.click(screen.getByRole("button", { name: "转换" }));

  expect(await screen.findByText("4.00")).toBeVisible();
  expect(screen.getByLabelText("人民币大写")).toHaveValue("肆元整");
  expect(screen.getByText("原输入：肆圆整 · 已规范")).toBeVisible();
  expect(
    screen.queryByText("已按标准写法转换：“圆”应写作“元”。"),
  ).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "数字转大写" }));
  expect(screen.getByLabelText("数字金额")).toHaveValue("4.00");
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
  expect(screen.getByRole("button", { name: "复制转换结果" })).toBeDisabled();
});

it("shows an actionable error when every copy mechanism fails", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(jsonResponse(negativeResponse)),
  );
  const user = userEvent.setup();
  vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(
    new Error("clipboard blocked"),
  );
  Object.defineProperty(document, "execCommand", {
    configurable: true,
    value: vi.fn().mockReturnValue(false),
  });
  renderWithProviders(<MoneyPage />);

  await user.type(screen.getByLabelText("数字金额"), "-128650.32");
  await user.click(screen.getByRole("button", { name: "转换" }));
  await user.click(screen.getByRole("button", { name: "复制快速读数" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "复制失败，请手动选择文本复制。",
  );
});
