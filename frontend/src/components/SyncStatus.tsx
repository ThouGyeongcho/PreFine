interface SyncStatusProps {
  stale: boolean;
  status: string;
  lastSucceededAt: string | null;
}

export function SyncStatus({
  stale,
  status,
  lastSucceededAt,
}: SyncStatusProps) {
  const labels: Record<string, string> = {
    fresh: "数据已同步",
    stale_refreshing: "数据已过期，正在刷新",
    failed_using_cache: "同步失败，正在显示上次数据",
  };
  const label =
    labels[status] ?? (stale ? "正在显示上次同步的数据" : "等待同步");
  const timestamp = lastSucceededAt
    ? new Intl.DateTimeFormat("zh-CN", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(lastSucceededAt))
    : "暂无成功同步记录";

  return (
    <div className="sync-status" role="status">
      <span
        className={`status-dot ${stale || status !== "fresh" ? "status-dot-warning" : ""}`}
        aria-hidden="true"
      />
      <span>{label}</span>
      <span className="muted">最近成功：{timestamp}</span>
    </div>
  );
}
