import { type FormEvent, type ReactNode, useState } from "react";

import { ApiError, apiRequest } from "../api/client";
import { AmountText } from "../components/AmountText";
import { copyText } from "../utils/clipboard";

type Direction = "number-to-uppercase" | "uppercase-to-number";
type CopyKey = "input" | "primary" | "grouped" | "quick" | "english";

interface ConversionPair {
  amount: string;
  uppercase: string;
}

interface MoneyConversionResponse extends ConversionPair {
  grouped: string;
  quick_read: string;
  english: string;
  normalization_note: string | null;
}

interface CopyButtonProps {
  copyKey: CopyKey;
  label: string;
  value: string;
  copiedKey: CopyKey | null;
  onCopy: (key: CopyKey, value: string) => void;
}

function CopyButton({
  copyKey,
  label,
  value,
  copiedKey,
  onCopy,
}: CopyButtonProps) {
  const copied = copiedKey === copyKey;

  return (
    <button
      className={`money-copy${copied ? " money-copy-done" : ""}`}
      type="button"
      aria-label={`复制${label}`}
      disabled={!value}
      onClick={() => onCopy(copyKey, value)}
    >
      {copied ? "已复制" : "复制"}
    </button>
  );
}

interface FormatCardProps extends CopyButtonProps {
  children: ReactNode;
}

function FormatCard({ children, ...copyProps }: FormatCardProps) {
  return (
    <article
      className="money-format-card"
      role="group"
      aria-label={copyProps.label}
    >
      <span className="money-label">{copyProps.label}</span>
      <div className="money-format-value">
        {copyProps.value ? (
          children
        ) : (
          <span className="money-placeholder">—</span>
        )}
      </div>
      <CopyButton {...copyProps} />
    </article>
  );
}

export function MoneyPage() {
  const [direction, setDirection] = useState<Direction>("number-to-uppercase");
  const [input, setInput] = useState("");
  const [result, setResult] = useState<MoneyConversionResponse | null>(null);
  const [lastPair, setLastPair] = useState<ConversionPair | null>(null);
  const [normalizedOriginal, setNormalizedOriginal] = useState<string | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [copiedKey, setCopiedKey] = useState<CopyKey | null>(null);
  const [copyError, setCopyError] = useState<string | null>(null);

  const numberToUppercase = direction === "number-to-uppercase";

  function clearTransientState() {
    setResult(null);
    setError(null);
    setCopiedKey(null);
    setCopyError(null);
    setNormalizedOriginal(null);
  }

  function selectDirection(nextDirection: Direction) {
    if (nextDirection === direction) return;

    setDirection(nextDirection);
    if (lastPair) {
      setInput(
        nextDirection === "uppercase-to-number"
          ? lastPair.uppercase
          : lastPair.amount,
      );
    } else {
      setInput("");
    }
    clearTransientState();
  }

  function changeInput(value: string) {
    setInput(value);
    setLastPair(null);
    clearTransientState();
  }

  async function convert(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!input) return;

    const submittedInput = input;
    setPending(true);
    setError(null);
    setCopiedKey(null);
    setCopyError(null);
    setNormalizedOriginal(null);

    try {
      const response = numberToUppercase
        ? await apiRequest<MoneyConversionResponse>("/api/money/to-uppercase", {
            method: "POST",
            body: JSON.stringify({ amount: input }),
          })
        : await apiRequest<MoneyConversionResponse>("/api/money/to-number", {
            method: "POST",
            body: JSON.stringify({ uppercase: input }),
          });

      const canonicalInput = numberToUppercase
        ? response.amount
        : response.uppercase;
      setInput(canonicalInput);
      setLastPair({ amount: response.amount, uppercase: response.uppercase });
      setResult(response);
      setNormalizedOriginal(
        !numberToUppercase &&
          response.normalization_note &&
          submittedInput !== canonicalInput
          ? submittedInput
          : null,
      );
    } catch (caught) {
      setResult(null);
      setLastPair(null);
      setError(
        caught instanceof ApiError ? caught.message : "转换失败，请稍后重试",
      );
    } finally {
      setPending(false);
    }
  }

  async function copyResult(key: CopyKey, value: string) {
    setCopyError(null);
    const copied = await copyText(value);
    if (copied) {
      setCopiedKey(key);
      return;
    }
    setCopiedKey(null);
    setCopyError("复制失败，请手动选择文本复制。");
  }

  const primaryResult = result
    ? numberToUppercase
      ? result.uppercase
      : result.amount
    : "";
  const inputLabel = numberToUppercase ? "数字金额" : "人民币大写";

  return (
    <div className="page-stack">
      <header className="page-header page-header-row money-page-header">
        <div>
          <p className="eyebrow">MONEY</p>
          <h1>金额转换</h1>
        </div>
        <div className="money-direction" role="group" aria-label="转换方向">
          <button
            type="button"
            aria-pressed={numberToUppercase}
            onClick={() => selectDirection("number-to-uppercase")}
          >
            数字转大写
          </button>
          <button
            type="button"
            aria-pressed={!numberToUppercase}
            onClick={() => selectDirection("uppercase-to-number")}
          >
            大写转数字
          </button>
        </div>
      </header>

      <form
        className="money-workbench"
        onSubmit={(event) => void convert(event)}
      >
        <div className="money-panels">
          <section className="money-panel">
            <div className="money-panel-heading">
              <span className="step-number">01</span>
              <h2>输入金额</h2>
            </div>
            <div className="money-field">
              <label className="money-label" htmlFor="money-input">
                {inputLabel}
              </label>
              <div className="money-content-box money-input-box">
                <textarea
                  className="money-input"
                  id="money-input"
                  value={input}
                  onChange={(event) => changeInput(event.target.value)}
                  placeholder={
                    numberToUppercase ? "例如：-128650.32" : "例如：壹佰元整"
                  }
                  inputMode={numberToUppercase ? "decimal" : "text"}
                  rows={3}
                />
                {normalizedOriginal ? (
                  <p className="money-input-note" role="status">
                    原输入：{normalizedOriginal} · 已规范
                  </p>
                ) : null}
                {error ? (
                  <p className="money-inline-error" role="alert">
                    {error}
                  </p>
                ) : null}
              </div>
              <CopyButton
                copyKey="input"
                label="输入金额"
                value={input}
                copiedKey={copiedKey}
                onCopy={(key, value) => void copyResult(key, value)}
              />
            </div>
          </section>

          <section className="money-panel">
            <div className="money-panel-heading">
              <span className="step-number">02</span>
              <h2>转换结果</h2>
            </div>
            <div className="money-field">
              <span className="money-label">
                {numberToUppercase ? "人民币大写" : "数字金额"}
              </span>
              <div className="money-content-box">
                <div
                  className="money-primary-result"
                  role={result ? "status" : undefined}
                  aria-label={result ? "转换结果" : undefined}
                >
                  {result ? (
                    numberToUppercase ? (
                      <AmountText value={primaryResult} kind="uppercase" />
                    ) : (
                      primaryResult
                    )
                  ) : (
                    <span className="money-placeholder">转换后显示</span>
                  )}
                </div>
              </div>
              <CopyButton
                copyKey="primary"
                label="转换结果"
                value={primaryResult}
                copiedKey={copiedKey}
                onCopy={(key, value) => void copyResult(key, value)}
              />
            </div>
          </section>
        </div>

        <button
          className="money-convert"
          type="submit"
          disabled={pending || !input}
        >
          {pending ? "正在转换…" : "转换"}
        </button>

        <section className="money-formats" aria-label="其他金额表示方式">
          <FormatCard
            copyKey="grouped"
            label="千分位"
            value={result?.grouped ?? ""}
            copiedKey={copiedKey}
            onCopy={(key, value) => void copyResult(key, value)}
          >
            {result?.grouped}
          </FormatCard>
          <FormatCard
            copyKey="quick"
            label="快速读数"
            value={result?.quick_read ?? ""}
            copiedKey={copiedKey}
            onCopy={(key, value) => void copyResult(key, value)}
          >
            {result ? (
              <AmountText value={result.quick_read} kind="quick" />
            ) : null}
          </FormatCard>
          <FormatCard
            copyKey="english"
            label="英文金额"
            value={result?.english ?? ""}
            copiedKey={copiedKey}
            onCopy={(key, value) => void copyResult(key, value)}
          >
            {result?.english}
          </FormatCard>
        </section>

        {copyError ? (
          <p className="money-copy-error" role="alert">
            {copyError}
          </p>
        ) : null}
      </form>
    </div>
  );
}
