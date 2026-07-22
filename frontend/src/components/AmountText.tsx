const UPPERCASE_DIGITS = new Set("零壹贰叁肆伍陆柒捌玖");
const UPPERCASE_UNITS = new Set("负拾佰仟万亿元角分整");
const QUICK_UNITS = new Set("万亿");

interface AmountTextProps {
  value: string;
  kind: "uppercase" | "quick";
  className?: string;
}

export function AmountText({ value, kind, className }: AmountTextProps) {
  const unitCharacters = kind === "uppercase" ? UPPERCASE_UNITS : QUICK_UNITS;

  return (
    <span className={className}>
      <span className="visually-hidden">{value}</span>
      <span aria-hidden="true">
        {[...value].map((character, index) => {
          const classNames = [];
          if (unitCharacters.has(character)) classNames.push("amount-unit");
          if (
            (kind === "uppercase" && UPPERCASE_DIGITS.has(character)) ||
            (kind === "quick" && /\d/.test(character))
          ) {
            classNames.push("amount-digit");
          }
          return (
            <span
              className={classNames.join(" ")}
              key={`${character}-${index}`}
            >
              {character}
            </span>
          );
        })}
      </span>
    </span>
  );
}
