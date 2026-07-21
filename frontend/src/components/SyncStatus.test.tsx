import { render, screen } from "@testing-library/react";

import { SyncStatus } from "./SyncStatus";

it.each([
  ["fresh", false, "数据已同步"],
  ["stale_refreshing", true, "数据已过期，正在刷新"],
  ["failed_using_cache", true, "同步失败，正在显示上次数据"],
])("describes %s distinctly", (status, stale, label) => {
  render(
    <SyncStatus
      status={status}
      stale={stale}
      lastSucceededAt="2026-07-21T01:00:00Z"
    />,
  );

  expect(screen.getByText(label)).toBeVisible();
});
