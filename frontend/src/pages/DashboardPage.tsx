import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { apiRequest } from "../api/client";
import type { CalendarMonth, TaxToolSettings } from "../api/types";

function currentMonth() {
  const today = new Date();
  return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;
}

export function DashboardPage() {
  const settings = useQuery({
    queryKey: ["tax-settings"],
    queryFn: () => apiRequest<TaxToolSettings>("/api/tools/tax/settings"),
  });
  const regionCode = settings.data?.default_region_code ?? "";
  const month = currentMonth();
  const calendar = useQuery({
    queryKey: ["calendar", regionCode, month],
    queryFn: () =>
      apiRequest<CalendarMonth>(
        `/api/calendar?region_code=${encodeURIComponent(regionCode)}&month=${month}`,
      ),
    enabled: Boolean(settings.data?.profile_complete && regionCode),
  });
  const summaryEnabled = Boolean(
    settings.data?.profile_complete && settings.data.default_region_code,
  );

  return (
    <div className="page-stack">
      <header className="page-header">
        <p className="eyebrow">OVERVIEW</p>
        <h1>工作台</h1>
        <p className="muted">集中使用日常财务工具，并查看税务配置状态。</p>
      </header>
      <section className="tool-grid" aria-label="工具入口">
        <Link to="/money" className="tool-card">
          <span className="tool-card-kicker">金额工具</span>
          <h2>金额转换</h2>
          <p>提供规范大写、快速读数和完整英文金额。</p>
          <span className="text-link">打开工具 →</span>
        </Link>
        <Link to="/calendar" className="tool-card">
          <span className="tool-card-kicker">税务工具</span>
          <h2>税收日历</h2>
          <p>查看 12366 官方原文与企业税务清单。</p>
          <span className="text-link">查看日历 →</span>
        </Link>
      </section>

      {settings.isPending ? <p className="muted">正在读取税务设置…</p> : null}
      {!settings.isPending && !summaryEnabled ? (
        <section className="notice-panel">
          <div>
            <span
              className="status-dot status-dot-warning"
              aria-hidden="true"
            />
            <strong>完成税务工具设置后启用个性化摘要</strong>
          </div>
          <Link to="/calendar#settings" className="button button-secondary">
            前往设置
          </Link>
        </section>
      ) : null}
      {summaryEnabled ? (
        <section
          className="settings-card dashboard-summary"
          aria-labelledby="tax-summary-title"
        >
          <div className="section-heading-row">
            <div>
              <p className="eyebrow">PERSONALIZED</p>
              <h2 id="tax-summary-title">近期税务摘要</h2>
            </div>
            <Link to="/calendar" className="text-link">
              查看完整日历
            </Link>
          </div>
          {calendar.isPending ? <p className="muted">正在生成摘要…</p> : null}
          {calendar.isError ? (
            <p className="inline-error" role="alert">
              摘要暂时不可用，请到税收日历查看同步状态。
            </p>
          ) : null}
          {calendar.data ? (
            calendar.data.personalized_events.length > 0 ? (
              <ul className="summary-list">
                {calendar.data.personalized_events.slice(0, 3).map((event) => (
                  <li key={event.key}>
                    <div>
                      <strong>{event.display_name}</strong>
                      <span>{event.matched_text}</span>
                    </div>
                    <time dateTime={event.end_date}>{event.end_date} 截止</time>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">本月暂无匹配事项。</p>
            )
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
