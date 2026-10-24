"""Opt-in acceptance of the 622-message export; private bytes stay outside Git."""

import hashlib
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import pytest
from bson import BSON
from bson.codec_options import CodecOptions

from src.ofw_import import import_ofw_messages
from src.ofw_parser import parse_ofw_message_report
from tests.fakes import FakeCollection
from tests.ofw_pdf_oracle import assert_oct16_layout_matches
from tests.ofw_private_checks import private_export_checks

EXPORT_SHA256 = "302ab8efa015c357d3bab42104ba0dbc40d20b366d8f6837d4dfa2e9a9031830"
ID_DIGEST = "ab1ae548423180e9e8c215b9c631ba94219f482641665cc5516a8351887402d8"
DEFAULT_EXPORT = Path("tests/fixtures/private/OFW_Messages_Report_2026-10-16_17-50-15.pdf")


@pytest.fixture(scope="module")
def oct16_export(request):
    explicit_path = request.config.getoption("--ofw-oct16-export")
    path = Path(explicit_path).expanduser() if explicit_path is not None else DEFAULT_EXPORT
    if not path.is_file():
        if explicit_path is not None:
            pytest.fail("explicit --ofw-oct16-export path must be a readable PDF", pytrace=False)
        pytest.skip("private October OFW export is not present; use --ofw-oct16-export")
    with private_export_checks():
        data = path.read_bytes()
        assert hashlib.sha256(data).hexdigest() == EXPORT_SHA256, "wrong private export"
        parsed = parse_ofw_message_report(data, document_id="oct16-acceptance-copy")
        yield data, parsed
        assert hashlib.sha256(path.read_bytes()).hexdigest() == EXPORT_SHA256, "source changed"


@pytest.mark.real_export
@private_export_checks()
def test_oct16_export_extraction_and_source_provenance(oct16_export):
    data, parsed = oct16_export
    metadata = parsed.metadata
    assert metadata.sha256 == EXPORT_SHA256
    assert metadata.page_count == 643
    assert metadata.expected_message_count == metadata.parsed_message_count == 622
    assert metadata.date_range_start == date(2024, 10, 16)
    assert metadata.date_range_end == date(2025, 10, 31)
    assert metadata.timezone == "America/Vancouver"
    assert len(parsed.messages) == len({message.message_id for message in parsed.messages}) == 622
    assert Counter(message.sent_at.utcoffset() for message in parsed.messages) == {
        timedelta(hours=-7): 322, timedelta(hours=-8): 300,
    }
    assert sum(len(message.attachments) for message in parsed.messages) == 257
    assert sum(bool(message.attachments) for message in parsed.messages) == 54
    assert sum(len(message.read_receipts) for message in parsed.messages) == 622
    for number, message in enumerate(parsed.messages, 1):
        assert message.source.document_id == metadata.document_id
        assert message.source.sha256 == EXPORT_SHA256
        assert message.source.source_type == "ofw_message_report"
        assert message.source.extraction_method == "native"
        assert message.source.confidence is None
        assert message.source.record_locator == f"message:{number}/622"
        assert message.report_message_number == number
        assert message.report_message_total == 622
        assert message.source_timezone == "America/Vancouver"
    assert_oct16_layout_matches(data, parsed.messages)


@pytest.mark.real_export
@private_export_checks()
def test_oct16_ids_and_import_replay_preserve_occurrences(oct16_export):
    data, parsed = oct16_export
    ids = [message.message_id for message in parsed.messages]
    assert hashlib.sha256("\n".join(ids).encode()).hexdigest() == ID_DIGEST
    another_copy = parse_ofw_message_report(data, document_id="separately-acquired-copy")
    assert ids == [message.message_id for message in another_copy.messages]

    collection = FakeCollection()
    first = import_ofw_messages(collection, parsed)
    assert (first.parsed_count, first.inserted_count, first.existing_count, first.occurrence_added_count) == (622, 622, 0, 622)
    # Exercise PyMongo's actual BSON codec, including UTC conversion, before replay.
    for key, document in collection.documents.items():
        collection.documents[key] = BSON.encode(document).decode(CodecOptions(tz_aware=True))
    replay = import_ofw_messages(collection, parsed)
    assert (replay.inserted_count, replay.existing_count, replay.occurrence_added_count) == (0, 622, 0)
    copied = import_ofw_messages(collection, another_copy)
    assert (copied.inserted_count, copied.existing_count, copied.occurrence_added_count) == (0, 622, 622)
    replay_copy = import_ofw_messages(collection, another_copy)
    assert (replay_copy.inserted_count, replay_copy.occurrence_added_count) == (0, 0)
    assert len(collection.documents) == 622
    for message in parsed.messages:
        stored = collection.find_one({"case_id": message.case_id, "message_id": message.message_id})
        assert stored["sent_at"] == message.sent_at
        assert stored["content_sha256"] == message.content_sha256
        assert stored["source"]["document_id"] == parsed.metadata.document_id
        assert stored["read_receipts"] == [r.model_dump(mode="python") for r in message.read_receipts]
        occurrences = stored["source_occurrences"]
        assert len(occurrences) == len({o["occurrence_key"] for o in occurrences}) == 2
        assert {o["source"]["document_id"] for o in occurrences} == {
            "oct16-acceptance-copy", "separately-acquired-copy",
        }
        assert stored["occurrence_version"] == 2
        for occurrence in occurrences:
            assert occurrence["source"]["sha256"] == EXPORT_SHA256
            assert occurrence["source"]["page"] == message.source.page
            assert occurrence["source"]["end_page"] == message.source.end_page
            assert occurrence["source"]["record_locator"] == message.source.record_locator
            assert occurrence["source_timezone"] == message.source_timezone
            assert occurrence["sent_at_raw"] == message.sent_at_raw
            assert occurrence["attachments"] == [a.model_dump(mode="python") for a in message.attachments]
