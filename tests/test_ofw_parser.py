from datetime import datetime

import pytest
from pydantic import ValidationError

from src.case_intelligence import OFWMessage, SourceRef
from src.ofw_parser import OFWParseError, parse_ofw_message_report_pages
from tests.ofw_sample import (
    SAMPLE_OFW_EDMONTON_PAGES,
    SAMPLE_OFW_PAGES,
    SAMPLE_PERSON_IDS,
    SAMPLE_SOURCE_SHA256,
)


def parse_sample(document_id="sample-ofw-export", source_sha256=SAMPLE_SOURCE_SHA256):
    return parse_ofw_message_report_pages(
        pages=SAMPLE_OFW_PAGES,
        document_id=document_id,
        source_sha256=source_sha256,
        person_id_by_display_name=SAMPLE_PERSON_IDS,
    )


def test_parser_uses_primary_message_markers_and_report_timezone():
    parsed = parse_sample()

    assert parsed.metadata.parsed_message_count == 2
    assert parsed.metadata.timezone == "America/Vancouver"
    first, second = parsed.messages
    assert first.sent_at.isoformat() == "2024-06-19T14:37:00-07:00"
    assert second.sent_at.isoformat() == "2026-01-30T15:25:00-08:00"
    assert first.body == "Current message only."
    assert "Quoted thread content" not in first.body
    assert second.sender_person_id == "person_laura_watson"
    assert second.recipient_person_ids == [
        "person_mitchel_watson",
        "person_sofia_rae_watson",
    ]
    assert second.read_receipts[0].first_viewed_at is None
    assert second.read_receipts[0].first_viewed_at_raw == "Never"
    assert second.attachments[0].filename == "example.pdf"
    assert second.attachments[1].filename == "photo, edited.JPG"
    assert second.attachments[1].raw_filename == "photo, edited. JPG"
    assert first.source.page == 1
    assert first.source.end_page == 1
    assert second.source.page == 2
    assert second.source.record_locator == "message:2/2"


def test_message_ids_are_stable_across_overlapping_exports():
    first = parse_sample(document_id="first", source_sha256="A" * 64)
    second = parse_sample(document_id="second", source_sha256="b" * 64)

    assert [message.message_id for message in first.messages] == [
        message.message_id for message in second.messages
    ]
    assert first.messages[0].source.sha256 != second.messages[0].source.sha256
    assert first.metadata.sha256 == "a" * 64


def test_message_ids_are_stable_when_report_timezone_changes():
    vancouver = parse_sample(document_id="vancouver", source_sha256="a" * 64)
    edmonton = parse_ofw_message_report_pages(
        pages=SAMPLE_OFW_EDMONTON_PAGES,
        document_id="edmonton",
        source_sha256="b" * 64,
        person_id_by_display_name=SAMPLE_PERSON_IDS,
    )

    assert [message.sent_at.isoformat() for message in vancouver.messages] != [
        message.sent_at.isoformat() for message in edmonton.messages
    ]
    assert [message.message_id for message in vancouver.messages] == [
        message.message_id for message in edmonton.messages
    ]


def test_parser_fails_closed_when_report_is_incomplete():
    incomplete = [page.replace("Contains: 2 selected messages", "Contains: 3 selected messages") for page in SAMPLE_OFW_PAGES]

    with pytest.raises(OFWParseError, match="marker count mismatch"):
        parse_ofw_message_report_pages(
            pages=incomplete,
            document_id="incomplete",
            source_sha256=SAMPLE_SOURCE_SHA256,
            person_id_by_display_name=SAMPLE_PERSON_IDS,
        )


def test_parser_fails_closed_when_attachment_list_is_not_fully_parsed():
    invalid = [page.replace("(200 KB)", "(unknown size)") for page in SAMPLE_OFW_PAGES]

    with pytest.raises(OFWParseError, match="fully parse OFW attachment list"):
        parse_ofw_message_report_pages(
            pages=invalid,
            document_id="invalid-attachment",
            source_sha256=SAMPLE_SOURCE_SHA256,
            person_id_by_display_name=SAMPLE_PERSON_IDS,
        )


def test_evidence_models_reject_naive_datetimes():
    with pytest.raises(ValidationError):
        OFWMessage(
            message_id="naive",
            sender_person_id="person_mitchel_watson",
            recipient_person_ids=["person_lindsay_alene_mcclean"],
            sent_at=datetime(2026, 1, 1, 12, 0),
            body="Body",
            source=SourceRef(
                document_id="doc",
                sha256="A" * 64,
                source_type="ofw_message_report",
            ),
        )


def test_source_hash_is_normalized_to_lowercase():
    source = SourceRef(
        document_id="doc",
        sha256="A" * 64,
        source_type="ofw_message_report",
    )

    assert source.sha256 == "a" * 64
