from decimal import Decimal

import pytest

from backend.app.money import (
    MoneyFormatError,
    format_amount,
    format_grouped_amount,
    format_quick_read,
    from_uppercase,
    parse_amount,
    to_english,
    to_uppercase,
)


@pytest.mark.parametrize(
    ("raw", "normalized", "uppercase"),
    [
        ("0", "0.00", "零元整"),
        ("-0.00", "0.00", "零元整"),
        ("1", "1.00", "壹元整"),
        ("0.01", "0.01", "零元零壹分"),
        ("10.01", "10.01", "壹拾元零壹分"),
        ("1001.10", "1001.10", "壹仟零壹元壹角"),
        ("100000001", "100000001.00", "壹亿零壹元整"),
        ("100010001", "100010001.00", "壹亿零壹万零壹元整"),
        ("1000000000000", "1000000000000.00", "壹万亿元整"),
        ("-128650.32", "-128650.32", "负壹拾贰万捌仟陆佰伍拾元叁角贰分"),
        (
            "999,999,999,999,999.99",
            "999999999999999.99",
            "玖佰玖拾玖万玖仟玖佰玖拾玖亿玖仟玖佰玖拾玖万玖仟玖佰玖拾玖元玖角玖分",
        ),
    ],
)
def test_amounts_round_trip_through_canonical_uppercase(
    raw: str,
    normalized: str,
    uppercase: str,
) -> None:
    amount = parse_amount(raw)

    assert format_amount(amount) == normalized
    assert to_uppercase(amount) == uppercase
    assert from_uppercase(uppercase) == amount


@pytest.mark.parametrize(
    ("raw", "grouped", "quick", "english"),
    [
        ("0", "0", "0", "Zero yuan only"),
        (
            "785934",
            "785,934",
            "78万5934",
            "Seven hundred eighty-five thousand nine hundred thirty-four yuan only",
        ),
        (
            "785934455.00",
            "785,934,455",
            "7亿8593万4455",
            "Seven hundred eighty-five million nine hundred thirty-four thousand "
            "four hundred fifty-five yuan only",
        ),
        (
            "1000000.32",
            "1,000,000.32",
            "100万0000.32",
            "One million yuan and thirty-two fen only",
        ),
        (
            "-12.50",
            "-12.50",
            "-12.50",
            "Negative twelve yuan and fifty fen only",
        ),
        (
            "999999999999999.99",
            "999,999,999,999,999.99",
            "999万亿9999亿9999万9999.99",
            "Nine hundred ninety-nine trillion nine hundred ninety-nine billion "
            "nine hundred ninety-nine million nine hundred ninety-nine thousand "
            "nine hundred ninety-nine yuan and ninety-nine fen only",
        ),
    ],
)
def test_amount_presentations(raw: str, grouped: str, quick: str, english: str) -> None:
    amount = parse_amount(raw)

    assert format_grouped_amount(amount) == grouped
    assert format_quick_read(amount) == quick
    assert to_english(amount) == english


def test_uppercase_parser_normalizes_round_to_yuan() -> None:
    assert from_uppercase("壹佰圆整") == Decimal("100.00")


@pytest.mark.parametrize(
    "raw",
    [
        "",
        ".5",
        "01",
        "1.",
        "1.001",
        "1e3",
        "￥1",
        " 1",
        "1 ",
        "1,00",
        "1,2345",
        "12,34",
        "1 000",
        "1,234,56.78",
        "1000000000000000",
    ],
)
def test_numeric_parser_rejects_noncanonical_or_out_of_range_input(raw: str) -> None:
    with pytest.raises(MoneyFormatError):
        parse_amount(raw)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "人民币壹元整",
        "一元整",
        "壹元正",
        "壹元",
        "壹元零角",
        "壹元零分",
        "负零元整",
        "壹拾零元整",
        "零元壹分",
        "壹佰万亿零零壹元整",
    ],
)
def test_uppercase_parser_only_accepts_encoder_output(raw: str) -> None:
    with pytest.raises(MoneyFormatError):
        from_uppercase(raw)


def test_money_public_functions_only_use_decimal_values() -> None:
    amount = parse_amount("12.34")
    restored = from_uppercase(to_uppercase(amount))

    assert isinstance(amount, Decimal)
    assert isinstance(restored, Decimal)
    assert restored == Decimal("12.34")
