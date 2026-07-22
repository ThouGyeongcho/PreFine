import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { apiRequest, ApiError } from "../api/client";
import type {
  CalendarMode,
  Region,
  TaxCatalogItem,
  TaxpayerType,
  TaxToolSettings as Settings,
} from "../api/types";

type EditableSettings = Pick<
  Settings,
  | "default_mode"
  | "taxpayer_type"
  | "selected_item_codes"
  | "default_region_code"
  | "reminder_days"
>;

interface TaxToolSettingsProps {
  settings: Settings;
  catalog: TaxCatalogItem[];
  regions: Region[];
  onSaved: (settings: Settings) => void;
}

function editable(settings: Settings): EditableSettings {
  return {
    default_mode: settings.default_mode,
    taxpayer_type: settings.taxpayer_type,
    selected_item_codes: [...settings.selected_item_codes],
    default_region_code: settings.default_region_code,
    reminder_days: [...settings.reminder_days],
  };
}

function parseReminderDays(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item !== "")
    .map(Number)
    .filter(Number.isInteger);
}

function errorMessage(error: unknown) {
  return error instanceof ApiError ? error.message : "保存失败，请稍后重试";
}

export function TaxToolSettings({
  settings,
  catalog,
  regions,
  onSaved,
}: TaxToolSettingsProps) {
  const [draft, setDraft] = useState<EditableSettings>(() =>
    editable(settings),
  );
  const [reminderDaysInput, setReminderDaysInput] = useState(() =>
    settings.reminder_days.join(","),
  );
  const [message, setMessage] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: (payload: EditableSettings) =>
      apiRequest<Settings>("/api/tools/tax/settings", {
        method: "PUT",
        body: JSON.stringify(payload),
      }),
    onSuccess: (saved) => {
      const normalized = editable(saved);
      setDraft(normalized);
      setReminderDaysInput(saved.reminder_days.join(","));
      setMessage("设置已保存");
      onSaved(saved);
    },
    onError: (error) => {
      setDraft(editable(settings));
      setReminderDaysInput(settings.reminder_days.join(","));
      setMessage(errorMessage(error));
    },
  });

  const testEmail = useMutation({
    mutationFn: () =>
      apiRequest<{ status: string }>("/api/tools/tax/test-email", {
        method: "POST",
      }),
    onSuccess: () => setMessage("测试邮件已发送"),
    onError: (error) => setMessage(errorMessage(error)),
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    save.mutate({
      ...draft,
      reminder_days: parseReminderDays(reminderDaysInput),
    });
  }

  function toggleItem(code: string, checked: boolean) {
    setDraft((current) => ({
      ...current,
      selected_item_codes: checked
        ? [...current.selected_item_codes, code]
        : current.selected_item_codes.filter((itemCode) => itemCode !== code),
    }));
  }

  function updateTaxpayerType(value: string) {
    const taxpayerType = (value || null) as TaxpayerType | null;
    setDraft((current) => ({
      ...current,
      taxpayer_type: taxpayerType,
      selected_item_codes: current.selected_item_codes.filter((code) => {
        const item = catalog.find((candidate) => candidate.code === code);
        return (
          taxpayerType !== null && item?.taxpayer_scope.includes(taxpayerType)
        );
      }),
    }));
  }

  return (
    <section
      id="settings"
      className="settings-card tax-settings"
      aria-label="税务工具设置"
    >
      <div className="section-heading-row">
        <div>
          <p className="eyebrow">仅影响税收日历</p>
          <h2>税务工具设置</h2>
        </div>
        <button
          className="button button-secondary"
          type="button"
          disabled={!settings.email_configured || testEmail.isPending}
          title={
            settings.email_configured
              ? undefined
              : "请先在系统环境变量中配置 SMTP"
          }
          onClick={() => testEmail.mutate()}
        >
          发送测试邮件
        </button>
      </div>
      <p className="tool-disclaimer">
        核定／关注事项由你自行配置；系统未连接电子税务局，也不会把这份清单视为企业真实税种核定结果。
      </p>

      <form className="tax-settings-form" onSubmit={submit}>
        <label>
          纳税人身份
          <select
            value={draft.taxpayer_type ?? ""}
            onChange={(event) => updateTaxpayerType(event.target.value)}
          >
            <option value="">请选择</option>
            <option value="general_taxpayer">增值税一般纳税人</option>
            <option value="small_scale_taxpayer">增值税小规模纳税人</option>
          </select>
        </label>
        <label>
          默认地区
          <select
            value={draft.default_region_code ?? ""}
            onChange={(event) =>
              setDraft((current) => ({
                ...current,
                default_region_code: event.target.value || null,
              }))
            }
          >
            <option value="">跟随当前选择</option>
            {regions.map((region) => (
              <option key={region.code} value={region.code}>
                {region.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          默认视图
          <select
            value={draft.default_mode}
            onChange={(event) =>
              setDraft((current) => ({
                ...current,
                default_mode: event.target.value as CalendarMode,
              }))
            }
          >
            <option value="official">官方税历</option>
            <option value="personalized">我的税务清单</option>
          </select>
        </label>
        <label>
          提前提醒天数
          <input
            value={reminderDaysInput}
            inputMode="numeric"
            onChange={(event) => setReminderDaysInput(event.target.value)}
          />
        </label>

        <fieldset className="tax-item-fieldset">
          <legend>关注税种与社保事项</legend>
          <div className="tax-item-grid">
            {catalog.map((item) => {
              const allowed =
                draft.taxpayer_type !== null &&
                item.taxpayer_scope.includes(draft.taxpayer_type);
              return (
                <label key={item.code}>
                  <input
                    type="checkbox"
                    checked={draft.selected_item_codes.includes(item.code)}
                    disabled={!allowed}
                    onChange={(event) =>
                      toggleItem(item.code, event.target.checked)
                    }
                  />
                  <span>{item.display_name}</span>
                </label>
              );
            })}
          </div>
        </fieldset>

        <div className="settings-actions">
          <button
            className="button button-primary"
            type="submit"
            disabled={save.isPending}
          >
            保存税务设置
          </button>
          {message ? (
            <span
              role={save.isError || testEmail.isError ? "alert" : "status"}
              className={
                save.isError || testEmail.isError
                  ? "inline-error"
                  : "save-status"
              }
            >
              {message}
            </span>
          ) : null}
        </div>
      </form>
    </section>
  );
}
