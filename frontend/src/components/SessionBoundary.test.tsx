import { act, screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";

import { notifyUnauthorized } from "../api/session";
import { renderWithProviders } from "../test/render";
import { SessionBoundary } from "./SessionBoundary";

it("clears cached business data and replaces the route on unauthorized", async () => {
  const { queryClient } = renderWithProviders(
    <SessionBoundary>
      <Routes>
        <Route path="/private" element={<h1>私密数据</h1>} />
        <Route path="/login" element={<h1>登录 PreFine</h1>} />
      </Routes>
    </SessionBoundary>,
    "/private",
  );
  queryClient.setQueryData(["sensitive"], { amount: "1.00" });

  act(() => notifyUnauthorized());

  expect(
    await screen.findByRole("heading", { name: "登录 PreFine" }),
  ).toBeVisible();
  expect(queryClient.getQueryData(["sensitive"])).toBeUndefined();
});

it("unsubscribes its unauthorized listener when unmounted", () => {
  const { queryClient, unmount } = renderWithProviders(
    <SessionBoundary>
      <Routes>
        <Route path="/private" element={<h1>私密数据</h1>} />
        <Route path="/login" element={<h1>登录 PreFine</h1>} />
      </Routes>
    </SessionBoundary>,
    "/private",
  );
  queryClient.setQueryData(["sensitive"], { amount: "1.00" });

  unmount();
  act(() => notifyUnauthorized());

  expect(queryClient.getQueryData(["sensitive"])).toEqual({ amount: "1.00" });
});
