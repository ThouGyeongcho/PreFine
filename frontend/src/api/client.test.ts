import { vi } from "vitest";

import { apiRequest } from "./client";
import { subscribeUnauthorized } from "./session";
import { jsonResponse } from "../test/render";

it("notifies the session boundary for every 401 response", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      jsonResponse(
        {
          code: "authentication_required",
          message: "登录已失效",
          details: {},
        },
        401,
      ),
    ),
  );
  const listener = vi.fn();
  const unsubscribe = subscribeUnauthorized(listener);

  await expect(apiRequest("/api/regions")).rejects.toMatchObject({
    status: 401,
  });

  expect(listener).toHaveBeenCalledOnce();
  unsubscribe();
});
