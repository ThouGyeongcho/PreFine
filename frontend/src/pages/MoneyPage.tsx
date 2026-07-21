import { type FormEvent, useState } from "react";

import { ApiError, apiRequest } from "../api/client";

type Direction = "number-to-uppercase" | "uppercase-to-number";

interface ConversionPair {
  amount: string;
  uppercase: string;
}

type UppercaseResponse = ConversionPair;
interface NumberResponse {
  amount: string;
}

export function MoneyPage() {
  const [direction, setDirection] = useState<Direction>("number-to-uppercase");
  const [input, setInput] = useState("");
  const [result, setResult] = useState("");
  const [lastPair, setLastPair] = useState<ConversionPair | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [copied, setCopied] = useState(false);

  const numberToUppercase = direction === "number-to-uppercase";

  async function convert(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!input) return;
    setPending(true);
    setError(null);
    setCopied(false);
    try {
      if (numberToUppercase) {
        const response = await apiRequest<UppercaseResponse>(
          "/api/money/to-uppercase",
          {
            method: "POST",
            body: JSON.stringify({ amount: input }),
          },
        );
        setLastPair(response);
        setResult(response.uppercase);
      } else {
        const response = await apiRequest<NumberResponse>(
          "/api/money/to-number",
          {
            method: "POST",
            body: JSON.stringify({ uppercase: input }),
          },
        );
        setLastPair({ amount: response.amount, uppercase: input });
        setResult(response.amount);
      }
    } catch (caught) {
      setResult("");
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
    setResult("");
    setError(null);
    setCopied(false);
  }

  async function copyResult() {
    if (!result) return;
    await navigator.clipboard.writeText(result);
    setCopied(true);
  }

  return (
    <div className="page-stack">
      <header className="page-header page-header-row">
        <div>
          <p className="eyebrow">MONEY</p>
          <h1>金额大小写转换</h1>
          <p className="muted">
            使用十进制定点规则处理人民币金额，结果可严格反向验证。
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
                  : "仅接受本系统生成的规范大写格式。"}
              </p>
            </div>
          </div>
          <label className="field-label" htmlFor="money-input">
            {numberToUppercase ? "数字金额" : "人民币大写"}
          </label>
          {numberToUppercase ? (
            <input
              id="money-input"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="例如：-128650.32"
              inputMode="decimal"
            />
          ) : (
            <textarea
              id="money-input"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="例如：负壹拾贰万捌仟陆佰伍拾元叁角贰分"
              rows={5}
            />
          )}
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
              <p>仅在输入通过完整校验后显示。</p>
            </div>
          </div>
          {result ? (
            <>
              <div
                className="conversion-output"
                role="status"
                aria-label="转换结果"
              >
                {result}
              </div>
              <button
                className="button button-secondary"
                type="button"
                onClick={() => void copyResult()}
              >
                复制结果
              </button>
              {copied ? <span className="copy-status">已复制</span> : null}
            </>
          ) : (
            <div className="empty-result">转换结果将在这里显示</div>
          )}
        </section>
      </form>

      <section className="rules-panel">
        <h2>当前转换规则</h2>
        <div className="rule-grid">
          <div>
            <strong>精度</strong>
            <span>固定到角分，拒绝三位及以上小数</span>
          </div>
          <div>
            <strong>范围</strong>
            <span>绝对值不超过 999,999,999,999,999.99</span>
          </div>
          <div>
            <strong>格式</strong>
            <span>反向解析要求与系统编码结果完全一致</span>
          </div>
        </div>
      </section>
    </div>
  );
}
