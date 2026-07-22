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

const originalExecCommand = document.execCommand;

afterEach(() => {
  Object.defineProperty(document, "execCommand", {
    configurable: true,
    value: originalExecCommand,
  });
});

it("shows every representation, copies plain text, and preserves the canonical pair", async () => {
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse(negativeResponse));
  vi.stubGlobal("fetch", fetchMock);
  const user = userEvent.setup();
  renderWithProviders(<MoneyPage />);

  expect(screen.getByRole("heading", { name: "金额转换" })).toBeVisible();
  await user.type(screen.getByLabelText("数字金额"), "-128650.32");
  await user.click(screen.getByRole("button", { name: "转换" }));

  expect(
    await screen.findByText("负壹拾贰万捌仟陆佰伍拾元叁角贰分"),
  ).toBeVisible();
  expect(screen.getByText("-128,650.32")).toBeVisible();
  expect(screen.getByText("-12万8650.32")).toHaveClass("visually-hidden");
  expect(screen.getByText(negativeResponse.english)).toBeVisible();
  expect(screen.queryByText("当前转换规则")).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "复制规范结果" }));
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
    vi.fn().mockResolvedValue(jsonResponse(negativeResponse)),
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

it("explains when round is normalized to the standard yuan spelling", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      jsonResponse({
        amount: "100.00",
        uppercase: "壹佰元整",
        grouped: "100",
        quick_read: "100",
        english: "One hundred yuan only",
        normalization_note: "已按标准写法转换：“圆”应写作“元”。",
      }),
    ),
  );
  const user = userEvent.setup();
  renderWithProviders(<MoneyPage />);

  await user.click(screen.getByRole("button", { name: "切换为大写转数字" }));
  expect(screen.getByLabelText("人民币大写")).toHaveProperty(
    "tagName",
    "TEXTAREA",
  );
  await user.type(screen.getByLabelText("人民币大写"), "壹佰圆整");
  await user.click(screen.getByRole("button", { name: "转换" }));

  expect(await screen.findByText("100.00")).toBeVisible();
  expect(screen.getByText("已按标准写法转换：“圆”应写作“元”。")).toBeVisible();
});

it("keeps only the latest item copy status", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(jsonResponse(negativeResponse)),
  );
  const user = userEvent.setup();
  renderWithProviders(<MoneyPage />);

  await user.type(screen.getByLabelText("数字金额"), "-128650.32");
  await user.click(screen.getByRole("button", { name: "转换" }));
  await user.click(screen.getByRole("button", { name: "复制千分位" }));
  expect(screen.getAllByText("已复制")).toHaveLength(1);

  await user.click(screen.getByRole("button", { name: "复制英文金额" }));
  expect(screen.getAllByText("已复制")).toHaveLength(1);
  expect(await navigator.clipboard.readText()).toBe(negativeResponse.english);
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
