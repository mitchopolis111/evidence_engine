import pytest

from src import timeline
from src.analysis import timeline as legacy_timeline


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Incident on 2025-11-20.", "2025-11-20"),
        ("Filename_2025/1/2.pdf", "2025-01-02"),
        ("Filed November 20, 2025", "2025-11-20"),
        ("Filed Nov. 20 2025", "2025-11-20"),
        ("Registry filing 16-NOV-2023", "2023-11-16"),
        ("Registry filing 3 Feb 2026", "2026-02-03"),
    ],
)
def test_extract_date_normalizes_supported_formats(text, expected):
    assert timeline.extract_date(text) == expected


def test_extract_date_returns_earliest_valid_date_in_text():
    text = "First November 20, 2025; later 2026-01-02."

    assert timeline.extract_date(text) == "2025-11-20"


def test_extract_date_skips_invalid_date_and_preserves_missing_date():
    assert timeline.extract_date("Invalid 2025-02-31; valid January 2, 2026") == (
        "2026-01-02"
    )
    assert timeline.extract_date("No verified date") is None
    assert timeline.extract_date("identifier12025-1-2x") is None


def test_build_timeline_item_does_not_invent_current_date():
    item = timeline.build_timeline_item("No date in this source", "UNSORTED")

    assert item["date"] is None


def test_analysis_timeline_is_a_compatibility_view_of_canonical_module():
    legacy_timeline.TIMELINE_STORE.clear()
    entry = legacy_timeline.TimelineEntry(
        id="entry-1",
        case_id="case-1",
        summary="Source summary",
        timestamp="2026-01-20",
        evidence_ids=["evidence-1"],
        predicted_type="UNSORTED",
        ocr_used=False,
        media_path=None,
        narrative={},
    )

    try:
        legacy_timeline.append_timeline_entry(entry)

        assert legacy_timeline.extract_date is timeline.extract_date
        assert legacy_timeline.TIMELINE_STORE is timeline.TIMELINE_STORE
        assert timeline.TIMELINE_STORE == [entry]
    finally:
        timeline.TIMELINE_STORE.clear()
