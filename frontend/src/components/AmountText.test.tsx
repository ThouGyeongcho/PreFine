import { render, screen } from "@testing-library/react";

import { AmountText } from "./AmountText";

it("colors only positional units in quick-reading text", () => {
  const { container } = render(
    <AmountText value="7亿8593万4455" kind="quick" />,
  );

  expect(screen.getByText("7亿8593万4455")).toHaveClass("visually-hidden");
  expect(
    [...container.querySelectorAll(".amount-unit")].map(
      (element) => element.textContent,
    ),
  ).toEqual(["亿", "万"]);
  expect(
    container.querySelector(".amount-unit")?.parentElement,
  ).toHaveAttribute("aria-hidden", "true");
});

it("colors uppercase units while leaving financial digits unaccented", () => {
  const { container } = render(
    <AmountText value="负壹拾贰万捌仟陆佰伍拾元叁角贰分" kind="uppercase" />,
  );

  expect(
    [...container.querySelectorAll(".amount-unit")].map(
      (element) => element.textContent,
    ),
  ).toEqual(["负", "拾", "万", "仟", "佰", "拾", "元", "角", "分"]);
  expect(
    [...container.querySelectorAll(".amount-digit")]
      .map((element) => element.textContent)
      .join(""),
  ).toBe("壹贰捌陆伍叁贰");
});
