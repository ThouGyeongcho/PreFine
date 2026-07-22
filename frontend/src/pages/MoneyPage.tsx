import { type FormEvent, type ReactNode, useState } from "react";

import { ApiError, apiRequest } from "../api/client";
import { AmountText } from "../components/AmountText";
import { copyText } from "../utils/clipboard";

type Direction = "number-to-uppercase" | "uppercase-to-number";
type CopyKey = "primary" | "grouped" | "quick" | "english";

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
  return (
    <div className="copy-action">
      <button
        className="button button-secondary"
        type="button"
        aria-label={`复制${label}`}
        onClick={() => onCopy(copyKey, value)}
      >
        复制
      </button>
      {copiedKey === copyKey ? (
        <span className="copy-status" role="status">
          已复制
        </span>
      ) : null}
    </div>
  );
}

interface ResultRowProps extends CopyButtonProps {
  children: ReactNode;
}

function ResultRow({ children, ...copyProps }: ResultRowProps) {
  return (
    <div className="result-row" role="group" aria-label={copyProps.label}>
      <div className="result-row-content">
        <span className="result-label">{copyProps.label}</span>
        <span className="result-value">{children}</span>
      </div>
      <CopyButton {...copyProps} />
    </div>
  );
}

export function MoneyPage() {
  const [direction, setDirection] = useState<Direction>("number-to-uppercase");
  const [input, setInput] = useState("");
  const [result, setResult] = useState<MoneyConversionResponse | null>(null);
  const [lastPair, setLastPair] = useState<ConversionPair | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [copiedKey, setCopiedKey] = useState<CopyKey | null>(null);
  const [copyError, setCopyError] = useState<string | null>(null);

  const numberToUppercase = direction === "number-to-uppercase";

  async function convert(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!input) return;
    setPending(true);
    setError(null);
    setCopiedKey(null);
    setCopyError(null);
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
      setLastPair({ amount: response.amount, uppercase: response.uppercase });
      setResult(response);
    } catch (caught) {
      setResult(null);
      setError(
        caught instanceof ApiError ? caught.message : "转换失败，请稍后重试",
      );
    } finally {
      setPending(false);
    }
  }

  function switchDirection() {
    const nextDirection = numberToUppercase
      ? "uppercase-to-number"
      : "number-to-uppercase";
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
    setResult(null);
    setError(null);
    setCopiedKey(null);
    setCopyError(null);
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

  return (
    <div className="page-stack">
      <header className="page-header page-header-row">
        <div>
          <p className="eyebrow">MONEY</p>
          <h1>金额转换</h1>
          <p className="muted">
            转换人民币数字与规范大写，并提供便于核对和使用的金额写法。
          </p>
        </div>
        <button
          className="button button-secondary"
          type="button"
          onClick={switchDirection}
        >
          {numberToUppercase ? "切换为大写转数字" : "切换为数字转大写"}
        </button>
      </header>

      <form
        className="conversion-grid"
        onSubmit={(event) => void convert(event)}
      >
        <section className="conversion-panel">
          <div className="panel-heading">
            <span className="step-number">01</span>
            <div>
              <h2>{numberToUppercase ? "输入数字金额" : "输入人民币大写"}</h2>
              <p>
                {numberToUppercase
                  ? "支持负数与规范千分位，最多两位小数。"
                  : "支持规范人民币大写，也可使用“圆”，转换后会提示标准写法。"}
              </p>
            </div>
          </div>
          <label className="field-label" htmlFor="money-input">
            {numberToUppercase ? "数字金额" : "人民币大写"}
          </label>
          <textarea
            className="money-input"
            id="money-input"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder={
              numberToUppercase
                ? "例如：-128650.32"
                : "例如：负壹拾贰万捌仟陆佰伍拾元叁角贰分"
            }
            inputMode={numberToUppercase ? "decimal" : "text"}
            rows={4}
          />
          {error ? (
            <div role="alert" className="inline-error">
              {error}
            </div>
          ) : null}
          <button
            className="button button-primary"
            type="submit"
            disabled={pending || !input}
          >
            {pending ? "正在转换…" : "转换"}
          </button>
        </section>

        <section className="conversion-panel conversion-result-panel">
          <div className="panel-heading">
            <span className="step-number">02</span>
            <div>
              <h2>规范结果</h2>
              <p>转换后可复制规范结果或任一种便捷写法。</p>
            </div>
          </div>
          {result ? (
            <div className="conversion-result-content">
              {result.normalization_note ? (
                <p className="normalization-note" role="status">
                  {result.normalization_note}
                </p>
              ) : null}
              <div
                className="primary-result"
                role="group"
                aria-label="规范结果"
              >
                <div
                  className="conversion-output"
                  role="status"
                  aria-label="转换结果"
                >
                  {numberToUppercase ? (
                    <AmountText value={primaryResult} kind="uppercase" />
                  ) : (
                    primaryResult
                  )}
                </div>
                <CopyButton
                  copyKey="primary"
                  label="规范结果"
                  value={primaryResult}
                  copiedKey={copiedKey}
                  onCopy={(key, value) => void copyResult(key, value)}
                />
              </div>

              <section className="convenient-results" aria-label="便捷写法">
                <h3>便捷写法</h3>
                <ResultRow
                  copyKey="grouped"
                  label="千分位"
                  value={result.grouped}
                  copiedKey={copiedKey}
                  onCopy={(key, value) => void copyResult(key, value)}
                >
                  {result.grouped}
                </ResultRow>
                <ResultRow
                  copyKey="quick"
                  label="快速读数"
                  value={result.quick_read}
                  copiedKey={copiedKey}
                  onCopy={(key, value) => void copyResult(key, value)}
                >
                  <AmountText value={result.quick_read} kind="quick" />
                </ResultRow>
                <ResultRow
                  copyKey="english"
                  label="英文金额"
                  value={result.english}
                  copiedKey={copiedKey}
                  onCopy={(key, value) => void copyResult(key, value)}
                >
                  {result.english}
                </ResultRow>
              </section>
              {copyError ? (
                <div className="inline-error copy-error" role="alert">
                  {copyError}
                </div>
              ) : null}
            </div>
          ) : (
            <div className="empty-result">转换结果将在这里显示</div>
          )}
        </section>
      </form>
    </div>
  );
}
