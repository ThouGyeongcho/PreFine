from decimal import Decimal

import pytest

from backend.app.money import (
    MoneyFormatError,
    format_amount,
    from_uppercase,
    parse_amount,
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
        "壹圆整",
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
