import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { apiRequest, ApiError } from "../api/client";
import type {
  CalendarMode,
  CalendarMonth,
  Region,
  TaxCatalogItem,
  TaxToolSettings,
} from "../api/types";
import { CalendarDetails } from "../components/CalendarDetails";
import { MonthCalendar } from "../components/MonthCalendar";
import { SyncStatus } from "../components/SyncStatus";
import { TaxToolSettings as TaxToolSettingsPanel } from "../components/TaxToolSettings";

function currentMonth() {
  const today = new Date();
  return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;
}

function messageFor(error: unknown) {
  return error instanceof ApiError
    ? error.message
    : "数据暂时不可用，请稍后重试";
}

export function CalendarPage() {
  const queryClient = useQueryClient();
  const [selectedRegion, setSelectedRegion] = useState(
    () => window.localStorage.getItem("tax-region") ?? "",
  );
  const [month, setMonth] = useState(currentMonth);
  const [modeOverride, setModeOverride] = useState<CalendarMode | null>(null);

  const regions = useQuery({
    queryKey: ["regions"],
    queryFn: () => apiRequest<Region[]>("/api/regions"),
  });
  const settings = useQuery({
    queryKey: ["tax-settings"],
    queryFn: () => apiRequest<TaxToolSettings>("/api/tools/tax/settings"),
  });
  const catalog = useQuery({
    queryKey: ["tax-catalog"],
    queryFn: () => apiRequest<TaxCatalogItem[]>("/api/tools/tax/catalog"),
  });

  const regionCode =
    selectedRegion ||
    settings.data?.default_region_code ||
    regions.data?.[0]?.code ||
    "";
  const mode = modeOverride ?? settings.data?.default_mode ?? "official";
  const calendar = useQuery({
    queryKey: ["calendar", regionCode, month],
    queryFn: () =>
      apiRequest<CalendarMonth>(
        `/api/calendar?region_code=${encodeURIComponent(regionCode)}&month=${month}`,
      ),
    enabled: regionCode !== "",
    refetchInterval: (query) =>
      query.state.data?.sync_status === "stale_refreshing" ? 2_000 : false,
  });

  const sync = useMutation({
    mutationFn: () =>
      apiRequest<CalendarMonth>("/api/tools/tax/sync", {
        method: "POST",
        body: JSON.stringify({ region_code: regionCode, month }),
      }),
    onSuccess: (result) =>
      queryClient.setQueryData(["calendar", regionCode, month], result),
  });

  function chooseRegion(code: string) {
    setSelectedRegion(code);
    window.localStorage.setItem("tax-region", code);
  }

  const loading =
    regions.isPending ||
    settings.isPending ||
    catalog.isPending ||
    calendar.isPending;
  const firstError =
    regions.error ?? settings.error ?? catalog.error ?? calendar.error;

  return (
    <div className="page-stack">
      <header className="page-header page-header-row">
        <div>
          <p className="eyebrow">TAX CALENDAR</p>
          <h1>税收日历</h1>
          <p className="muted">
            以 12366 官方数据为底稿，按你的身份和关注事项生成清单。
          </p>
        </div>
        <div className="calendar-controls">
          <label>
            地区
            <select
              value={regionCode}
              onChange={(event) => chooseRegion(event.target.value)}
            >
              {(regions.data ?? []).map((region) => (
                <option value={region.code} key={region.code}>
                  {region.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            月份
            <input
              type="month"
              value={month}
              onChange={(event) => setMonth(event.target.value)}
            />
          </label>
          <button
            className="button button-secondary"
            type="button"
            disabled={!regionCode || sync.isPending}
            onClick={() => sync.mutate()}
          >
            {sync.isPending ? "正在同步…" : "立即同步"}
          </button>
        </div>
      </header>

      {loading ? <p className="muted">正在加载税历…</p> : null}
      {firstError ? (
        <p className="inline-error" role="alert">
          {messageFor(firstError)}
        </p>
      ) : null}
      {sync.error ? (
        <p className="inline-error" role="alert">
          {messageFor(sync.error)}
        </p>
      ) : null}

      {calendar.data ? (
        <>
          <div className="calendar-toolbar">
            <div className="view-tabs" role="tablist" aria-label="日历视图">
              <button
                className={
                  mode === "official" ? "view-tab view-tab-active" : "view-tab"
                }
                type="button"
                role="tab"
                aria-selected={mode === "official"}
                onClick={() => setModeOverride("official")}
              >
                官方税历
              </button>
              <button
                className={
                  mode === "personalized"
                    ? "view-tab view-tab-active"
                    : "view-tab"
                }
                type="button"
                role="tab"
                aria-selected={mode === "personalized"}
                onClick={() => setModeOverride("personalized")}
              >
                我的税务清单
              </button>
            </div>
            <SyncStatus
              stale={calendar.data.stale}
              status={calendar.data.sync_status}
              lastSucceededAt={calendar.data.last_succeeded_at}
            />
          </div>
          <div className="calendar-layout">
            <MonthCalendar
              month={month}
              mode={mode}
              officialEvents={calendar.data.official_events}
              personalizedEvents={calendar.data.personalized_events}
            />
            <CalendarDetails
              mode={mode}
              officialEvents={calendar.data.official_events}
              personalizedEvents={calendar.data.personalized_events}
              sourceUrl={calendar.data.source_url}
              profileComplete={calendar.data.profile_complete}
              onShowOfficial={() => setModeOverride("official")}
            />
          </div>
        </>
      ) : null}

      {settings.data && catalog.data && regions.data ? (
        <TaxToolSettingsPanel
          settings={settings.data}
          catalog={catalog.data}
          regions={regions.data}
          onSaved={(saved) => {
            queryClient.setQueryData(["tax-settings"], saved);
            void queryClient.invalidateQueries({ queryKey: ["calendar"] });
          }}
        />
      ) : null}
    </div>
  );
}
