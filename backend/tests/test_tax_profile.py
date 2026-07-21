from datetime import date

from backend.app.calendar import CachedCalendarEvent
from backend.app.tax_profile import TaxToolSettings, filter_events, load_catalog


def make_event(
    text: str,
    *items: str,
) -> CachedCalendarEvent:
    return CachedCalendarEvent(
        source_event_id="event-1",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 15),
        bssz=text,
        split_items=tuple(items),
        source_agency="国家税务总局",
        source_created_at="2025-12-29 13:40:56",
        source_order=0,
    )


def settings(
    taxpayer_type: str = "general_taxpayer",
    *selected_codes: str,
) -> TaxToolSettings:
    return TaxToolSettings(
        taxpayer_type=taxpayer_type,
        selected_item_codes=list(selected_codes),
    )


def test_incomplete_profile_does_not_guess_personalized_items() -> None:
    event = make_event("增值税", "增值税")

    assert filter_events([event], TaxToolSettings(), load_catalog()) == []


def test_common_and_selected_items_are_included() -> None:
    event = make_event("增值税、企业所得税", "增值税", "企业所得税")

    result = filter_events(
        [event],
        settings("general_taxpayer", "vat", "corporate_income_tax"),
        load_catalog(),
    )

    assert [item.item_code for item in result] == ["vat", "corporate_income_tax"]
    assert [item.display_name for item in result] == ["增值税", "企业所得税"]


def test_taxpayer_specific_item_is_filtered_by_explicit_scope() -> None:
    event = make_event(
        "增值税一般纳税人、增值税小规模纳税人",
        "增值税一般纳税人",
        "增值税小规模纳税人",
    )

    general = filter_events(
        [event],
        settings("general_taxpayer", "vat_general", "vat_small_scale"),
        load_catalog(),
    )
    small = filter_events(
        [event],
        settings("small_scale_taxpayer", "vat_general", "vat_small_scale"),
        load_catalog(),
    )

    assert [item.item_code for item in general] == ["vat_general"]
    assert [item.item_code for item in small] == ["vat_small_scale"]


def test_restricted_prefix_rule_maps_without_fuzzy_similarity() -> None:
    event = make_event("申报缴纳增值税", "申报缴纳增值税")

    result = filter_events(
        [event],
        settings("general_taxpayer", "vat"),
        load_catalog(),
    )

    assert result[0].item_code == "vat"
    assert result[0].matched_text == "申报缴纳增值税"


def test_unknown_text_is_visible_for_confirmation_with_official_context() -> None:
    event = make_event("新出现的上游事项", "新出现的上游事项")

    result = filter_events(
        [event],
        settings("general_taxpayer", "vat"),
        load_catalog(),
    )

    assert len(result) == 1
    assert result[0].category == "其他待确认"
    assert result[0].item_code is None
    assert result[0].official_text == "新出现的上游事项"
    assert result[0].matched_text == "新出现的上游事项"
    assert result[0].start_date == event.start_date
    assert result[0].end_date == event.end_date
    assert result[0].needs_confirmation is True


def test_filter_never_mutates_or_reconstructs_official_text() -> None:
    event = make_event("申报缴纳增值税、未知事项", "申报缴纳增值税", "未知事项")
    before = event.bssz

    filter_events([event], settings("general_taxpayer", "vat"), load_catalog())

    assert event.bssz == before


def test_reminder_days_are_unique_sorted_and_limited_to_zero_through_thirty() -> None:
    configured = TaxToolSettings(reminder_days=[1, 7, 3, 7, 0])
    assert configured.reminder_days == [7, 3, 1, 0]
