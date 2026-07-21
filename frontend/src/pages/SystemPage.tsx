import { useQuery } from "@tanstack/react-query";

import { apiRequest } from "../api/client";
import type { HealthStatus, TaxToolSettings } from "../api/types";

export function SystemPage() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => apiRequest<HealthStatus>("/api/health"),
  });
  const taxSettings = useQuery({
    queryKey: ["tax-settings"],
    queryFn: () => apiRequest<TaxToolSettings>("/api/tools/tax/settings"),
  });

  return (
    <div className="page-stack">
      <header className="page-header">
        <p className="eyebrow">DEPLOYMENT</p>
        <h1>系统设置</h1>
        <p className="muted">只展示部署状态；敏感配置由环境变量管理。</p>
      </header>
      <section className="settings-card">
        <h2>运行状态</h2>
        {health.isPending ? <p>正在检查…</p> : null}
        {health.data ? (
          <dl className="status-list">
            <div>
              <dt>应用</dt>
              <dd>{health.data.status}</dd>
            </div>
            <div>
              <dt>数据库</dt>
              <dd>{health.data.database}</dd>
            </div>
            <div>
              <dt>调度器</dt>
              <dd>{health.data.scheduler}</dd>
            </div>
            <div>
              <dt>邮件提醒</dt>
              <dd>
                {taxSettings.isPending
                  ? "正在检查"
                  : taxSettings.data?.email_configured
                    ? "已配置"
                    : "未配置"}
              </dd>
            </div>
            <div>
              <dt>版本</dt>
              <dd>{health.data.version}</dd>
            </div>
          </dl>
        ) : null}
      </section>
    </div>
  );
}
