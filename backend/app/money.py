import re
from decimal import Decimal, InvalidOperation

AMOUNT_PATTERN = re.compile(
    r"^-?(?:0|[1-9]\d*|[1-9]\d{0,2}(?:,\d{3})+)(?:\.\d{1,2})?$"
)
MAX_AMOUNT = Decimal("999999999999999.99")
QUANTUM = Decimal("0.01")
UPPERCASE_FORMAT_MESSAGE = (
    "请输入完整的人民币大写金额，例如“壹佰元整”。"
    "可使用“圆”，系统会转换为标准写法“元”。"
)

DIGITS = "零壹贰叁肆伍陆柒捌玖"
DIGIT_VALUES = {character: index for index, character in enumerate(DIGITS)}
NONZERO_DIGITS = DIGITS[1:]
SMALL_UNITS = ((1000, "仟"), (100, "佰"), (10, "拾"), (1, ""))
UNIT_VALUES = {"仟": 1000, "佰": 100, "拾": 10}
ENGLISH_ONES = (
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
)
ENGLISH_TENS = (
    "",
    "",
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
)
ENGLISH_SCALES = ("", "thousand", "million", "billion", "trillion")


class MoneyFormatError(ValueError):
    """Raised when an amount is outside the toolkit's canonical grammar."""


def parse_amount(value: str) -> Decimal:
    """Parse a canonical numeric amount without involving binary floats."""

    if not isinstance(value, str) or AMOUNT_PATTERN.fullmatch(value) is None:
        if isinstance(value, str) and re.fullmatch(
            r"^-?(?:0|[1-9]\d*|[1-9]\d{0,2}(?:,\d{3})+)\.\d{3,}$",
            value,
        ):
            raise MoneyFormatError("金额最多保留两位小数。")
        raise MoneyFormatError("请输入数字金额，可使用规范千分位，最多保留两位小数。")
    try:
        amount = Decimal(value.replace(",", ""))
    except InvalidOperation as error:
        raise MoneyFormatError("请输入有效金额") from error
    if abs(amount) > MAX_AMOUNT:
        raise MoneyFormatError("金额绝对值不能超过 999,999,999,999,999.99。")
    if amount == 0:
        return Decimal("0.00")
    return amount.quantize(QUANTUM)


def format_amount(value: Decimal) -> str:
    amount = _validated_decimal(value)
    return f"{amount:.2f}"


def format_grouped_amount(value: Decimal) -> str:
    """Format an amount with three-digit grouping and significant cents."""

    amount = _validated_decimal(value)
    sign = "-" if amount < 0 else ""
    integer_text, fraction_text = f"{abs(amount):.2f}".split(".")
    result = f"{sign}{int(integer_text):,}"
    if fraction_text != "00":
        result += f".{fraction_text}"
    return result


def format_quick_read(value: Decimal) -> str:
    """Group exact digits by Chinese four-place units without rounding."""

    amount = _validated_decimal(value)
    sign = "-" if amount < 0 else ""
    integer_text, fraction_text = f"{abs(amount):.2f}".split(".")
    groups: list[str] = []
    remaining = integer_text
    while remaining:
        groups.insert(0, remaining[-4:])
        remaining = remaining[:-4]

    last_group_index = len(groups) - 1
    if fraction_text == "00":
        while last_group_index > 0 and groups[last_group_index] == "0000":
            last_group_index -= 1

    parts: list[str] = []
    for index, group in enumerate(groups[: last_group_index + 1]):
        position = len(groups) - index - 1
        group_text = group if index == 0 else group.zfill(4)
        parts.append(group_text)
        parts.append(_quick_read_unit(position))

    result = f"{sign}{''.join(parts)}"
    if fraction_text != "00":
        result += f".{fraction_text}"
    return result


def to_english(value: Decimal) -> str:
    """Spell an amount in complete sentence-case English words."""

    amount = _validated_decimal(value)
    negative = amount < 0
    absolute = abs(amount)
    integer = int(absolute)
    cents = int((absolute - Decimal(integer)) * 100)

    parts = []
    if negative:
        parts.append("negative")
    parts.extend((_integer_to_english(integer), "yuan"))
    if cents:
        parts.extend(("and", _below_thousand_to_english(cents), "fen"))
    parts.append("only")
    result = " ".join(parts)
    return result[0].upper() + result[1:]


def to_uppercase(value: Decimal) -> str:
    """Encode a Decimal amount as the toolkit's canonical RMB uppercase text."""

    amount = _validated_decimal(value)
    if amount == 0:
        return "零元整"

    negative = amount < 0
    absolute = abs(amount)
    integer = int(absolute)
    cents = int((absolute - Decimal(integer)) * 100)
    jiao, fen = divmod(cents, 10)

    parts = ["负"] if negative else []
    parts.extend((_encode_integer(integer), "元"))
    if jiao == 0 and fen == 0:
        parts.append("整")
    else:
        if jiao:
            parts.extend((DIGITS[jiao], "角"))
        if fen:
            if jiao == 0:
                parts.append("零")
            parts.extend((DIGITS[fen], "分"))
    return "".join(parts)


def from_uppercase(value: str) -> Decimal:
    """Parse canonical uppercase text plus the common currency unit alias 圆."""

    if not isinstance(value, str) or not value:
        raise MoneyFormatError(UPPERCASE_FORMAT_MESSAGE)

    normalized = value.replace("圆", "元")
    negative = normalized.startswith("负")
    unsigned = normalized[1:] if negative else normalized
    if unsigned.count("元") != 1:
        raise MoneyFormatError(UPPERCASE_FORMAT_MESSAGE)

    integer_text, fraction_text = unsigned.split("元", maxsplit=1)
    try:
        integer = _parse_integer(integer_text)
        cents = _parse_fraction(fraction_text)
        amount = Decimal(integer) + (Decimal(cents) / 100)
    except (KeyError, ValueError) as error:
        raise MoneyFormatError(UPPERCASE_FORMAT_MESSAGE) from error

    if negative:
        amount = -amount
    amount = amount.quantize(QUANTUM)
    if abs(amount) > MAX_AMOUNT or to_uppercase(amount) != normalized:
        raise MoneyFormatError(UPPERCASE_FORMAT_MESSAGE)
    return amount


def _quick_read_unit(position: int) -> str:
    if position == 0:
        return ""
    if position % 2 == 0:
        return "亿" * (position // 2)
    return f"万{'亿' * (position // 2)}"


def _integer_to_english(value: int) -> str:
    if value == 0:
        return "zero"

    chunks: list[str] = []
    position = 0
    remaining = value
    while remaining:
        remaining, chunk = divmod(remaining, 1000)
        if chunk:
            words = _below_thousand_to_english(chunk)
            scale = ENGLISH_SCALES[position]
            chunks.append(f"{words} {scale}".strip())
        position += 1
    return " ".join(reversed(chunks))


def _below_thousand_to_english(value: int) -> str:
    parts: list[str] = []
    hundreds, remainder = divmod(value, 100)
    if hundreds:
        parts.extend((ENGLISH_ONES[hundreds], "hundred"))
    if remainder < 20:
        if remainder:
            parts.append(ENGLISH_ONES[remainder])
    else:
        tens, ones = divmod(remainder, 10)
        parts.append(
            ENGLISH_TENS[tens]
            if ones == 0
            else f"{ENGLISH_TENS[tens]}-{ENGLISH_ONES[ones]}"
        )
    return " ".join(parts)


def _validated_decimal(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise MoneyFormatError("金额必须使用十进制定点数")
    quantized = value.quantize(QUANTUM)
    if value != quantized:
        raise MoneyFormatError("金额最多保留两位小数")
    if abs(quantized) > MAX_AMOUNT:
        raise MoneyFormatError("金额绝对值不能超过 999,999,999,999,999.99。")
    return Decimal("0.00") if quantized == 0 else quantized


def _encode_integer(value: int) -> str:
    if value == 0:
        return "零"
    high, low = divmod(value, 100_000_000)
    if high == 0:
        return _encode_below_yi(low)

    result = f"{_encode_below_yi(high)}亿"
    if low:
        if low < 10_000_000:
            result += "零"
        result += _encode_below_yi(low)
    return result


def _encode_below_yi(value: int) -> str:
    high, low = divmod(value, 10_000)
    if high == 0:
        return _encode_group(low)

    result = f"{_encode_group(high)}万"
    if low:
        if low < 1000:
            result += "零"
        result += _encode_group(low)
    return result


def _encode_group(value: int) -> str:
    parts: list[str] = []
    zero_pending = False
    for divisor, unit in SMALL_UNITS:
        digit = (value // divisor) % 10
        if digit:
            if zero_pending:
                parts.append("零")
            parts.extend((DIGITS[digit], unit))
            zero_pending = False
        elif parts and value % divisor:
            zero_pending = True
    return "".join(parts)


def _parse_integer(text: str) -> int:
    if text == "零":
        return 0
    if not text or text.count("亿") > 1:
        raise ValueError("invalid integer")
    if "亿" not in text:
        return _parse_below_yi(text)

    high_text, low_text = text.split("亿")
    if not high_text:
        raise ValueError("missing high section")
    high = _parse_below_yi(high_text)
    low = _parse_below_yi(low_text) if low_text else 0
    return high * 100_000_000 + low


def _parse_below_yi(text: str) -> int:
    if not text or text.count("万") > 1:
        raise ValueError("invalid section")
    if "万" not in text:
        return _parse_group(text)

    high_text, low_text = text.split("万")
    if not high_text:
        raise ValueError("missing ten-thousand section")
    high = _parse_group(high_text)
    low = _parse_group(low_text) if low_text else 0
    return high * 10_000 + low


def _parse_group(text: str) -> int:
    if not text:
        return 0
    total = 0
    pending_digit: int | None = None
    previous_unit = 10_000
    for character in text:
        if character == "零":
            pending_digit = 0
            continue
        if character in DIGIT_VALUES:
            if pending_digit not in (None, 0):
                raise ValueError("adjacent digits")
            pending_digit = DIGIT_VALUES[character]
            continue
        unit = UNIT_VALUES[character]
        if pending_digit in (None, 0) or unit >= previous_unit:
            raise ValueError("invalid unit sequence")
        total += pending_digit * unit
        pending_digit = None
        previous_unit = unit
    if pending_digit is not None:
        total += pending_digit
    if total >= 10_000:
        raise ValueError("group overflow")
    return total


def _parse_fraction(text: str) -> int:
    if text == "整":
        return 0
    if len(text) == 2 and text[0] in NONZERO_DIGITS and text[1] == "角":
        return DIGIT_VALUES[text[0]] * 10
    if (
        len(text) == 4
        and text[0] in NONZERO_DIGITS
        and text[1] == "角"
        and text[2] in NONZERO_DIGITS
        and text[3] == "分"
    ):
        return DIGIT_VALUES[text[0]] * 10 + DIGIT_VALUES[text[2]]
    if (
        len(text) == 3
        and text[0] == "零"
        and text[1] in NONZERO_DIGITS
        and text[2] == "分"
    ):
        return DIGIT_VALUES[text[1]]
    raise ValueError("invalid fraction")
