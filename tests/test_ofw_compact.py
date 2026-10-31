"""Synthetic compact PDF fixtures contain no private report content."""

import fitz
import pytest

from src.ofw_import import import_ofw_messages
from src.ofw_parser import OFWParseError, parse_ofw_message_report
from tests.fakes import FakeCollection
from tests.ofw_sample import SAMPLE_PERSON_IDS


def compact_pdf():
    with fitz.open() as pdf:
        page = pdf.new_page(width=612, height=792)

        def header(page, y, number, sent, sender, recipient, subject):
            page.insert_text((34, y), f"Message {number} of 2", fontsize=12)
            for x, offset, text in [(29, 25, "SENT"), (312, 25, "FROM"),
                                    (29, 53, "TO"), (29, 81, "SUBJECT")]:
                page.insert_text((x, y + offset), text, fontsize=8)
            for x, offset, text in [(79, 25, sent), (362, 25, sender),
                                    (79, 53, recipient), (79, 81, subject)]:
                page.insert_text((x, y + offset), text, fontsize=12)

        header(page, 50, 1, "06/19/2024 2:37 PM", "Parent Alpha",
               "Parent Beta (First Viewed: 06/20/2024 10:18 AM)", "Testing")
        page.insert_text((31, 160), "Current message only.")
        header(page, 220, 2, "01/30/2026 3:25 PM", "Parent Beta",
               "Parent Alpha (First Viewed: Never)", "Wrapped subject")
        page.insert_text((79, 317), "continued", fontsize=12)
        page.insert_text((31, 350), "Body begins here.")
        page.insert_text((520, 765), "Page 1 of 2", fontsize=10)
        page = pdf.new_page(width=612, height=792)
        page.insert_text((31, 50), "Body ends here.")
        page.insert_text((31, 80), "See Attachments: example.pdf (1.6 MB)")
        page.insert_text((520, 765), "Page 2 of 2", fontsize=10)
        return pdf.tobytes()


def test_compact_pdf_requires_explicit_timezone():
    with pytest.raises(OFWParseError, match="explicit report_timezone"):
        parse_ofw_message_report(compact_pdf(), "compact", person_id_by_display_name=SAMPLE_PERSON_IDS)


def test_compact_pdf_headers_wrapping_pages_and_supplied_timezone_provenance():
    data = compact_pdf()
    parsed = parse_ofw_message_report(
        data, "compact", person_id_by_display_name=SAMPLE_PERSON_IDS, report_timezone="America/Vancouver",
    )
    first, second = parsed.messages
    assert parsed.metadata.timezone_basis == "supplied"
    assert parsed.metadata.date_range_basis == "messages"
    assert parsed.metadata.expected_message_count == 2
    assert first.sent_at.isoformat() == "2024-06-19T14:37:00-07:00"
    assert first.read_at.isoformat() == "2024-06-20T10:18:00-07:00"
    assert first.body == "Current message only."
    assert second.subject == "Wrapped subject continued"
    assert " ".join(second.body.split()) == "Body begins here. Body ends here."
    assert second.read_receipts[0].first_viewed_at_raw == "Never"
    assert second.attachments[0].filename == "example.pdf"
    assert (second.source.page, second.source.end_page) == (1, 2)
    assert second.source.record_locator == "message:2/2"
    assert second.source_timezone_basis == "supplied"
    collection = FakeCollection()
    import_ofw_messages(collection, parsed)
    stored = collection.find_one({"message_id": second.message_id})
    assert stored["source_occurrences"][0]["source_timezone_basis"] == "supplied"
    assert stored["source_occurrences"][0]["body"] == second.body


def test_compact_pdf_rejects_invalid_timezone():
    with pytest.raises(OFWParseError, match="unknown OFW report timezone"):
        parse_ofw_message_report(compact_pdf(), "compact", report_timezone="Invalid/Zone")


def test_same_source_reinterpreted_in_another_timezone_is_rejected():
    from src.ofw_import import OFWImportConflict
    data = compact_pdf()
    reports = [parse_ofw_message_report(data, f"acquisition-{zone}", report_timezone=zone,
                                       person_id_by_display_name=SAMPLE_PERSON_IDS)
               for zone in ["America/Vancouver", "America/Edmonton"]]
    collection = FakeCollection()
    import_ofw_messages(collection, reports[0])
    with pytest.raises(OFWImportConflict, match="source record"):
        import_ofw_messages(collection, reports[1])
    assert len(collection.documents) == 2
