"""Opt-in compact-report acceptance; never put private bytes in Git/CI."""

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
from tests.ofw_compact_oracle import audit_compact_text
from tests.ofw_private_checks import private_export_checks
from tests.test_ofw_oct16_export import oct16_export  # noqa: F401

EXPORT_SHA256 = "17def0326769159715bbaed60978e9b620a6cc92b8c42850757edf43599f0988"


@pytest.fixture(scope="module")
def oct30_export(request):
    explicit = request.config.getoption("--ofw-oct30-export")
    if explicit is None:
        pytest.skip("private October 30 export is absent; use --ofw-oct30-export and --ofw-oct30-timezone")
    path = Path(explicit).expanduser()
    if not explicit or not path.is_file():
        pytest.fail("explicit --ofw-oct30-export path must be a readable PDF", pytrace=False)
    zone = request.config.getoption("--ofw-oct30-timezone")
    if not zone:
        pytest.fail("--ofw-oct30-timezone is required; PDF does not declare its timezone", pytrace=False)
    with private_export_checks():
        data = path.read_bytes()
        assert hashlib.sha256(data).hexdigest() == EXPORT_SHA256
        parsed = parse_ofw_message_report(data, "oct30-acceptance-copy", report_timezone=zone)
        yield data, parsed
        assert hashlib.sha256(path.read_bytes()).hexdigest() == EXPORT_SHA256


@pytest.mark.real_export
@private_export_checks()
def test_oct30_extraction_and_independent_text_audit(oct30_export):
    data, parsed = oct30_export
    meta = parsed.metadata
    assert meta.page_count == 498
    assert meta.expected_message_count == meta.parsed_message_count == 1174
    assert meta.date_range_start == date(2024, 6, 19)
    assert meta.date_range_end == date(2026, 10, 29)
    assert meta.timezone_basis == "supplied" and meta.date_range_basis == "messages"
    assert meta.generated_at_raw is None
    assert len({m.message_id for m in parsed.messages}) == 1174
    assert sum(len(m.read_receipts) for m in parsed.messages) == 1176
    assert sum(r.first_viewed_at is None for m in parsed.messages for r in m.read_receipts) == 6
    assert sum(len(m.attachments) for m in parsed.messages) == 295
    assert sum(bool(m.attachments) for m in parsed.messages) == 81
    if meta.timezone == "America/Vancouver":
        assert hashlib.sha256("\n".join(m.message_id for m in parsed.messages).encode()).hexdigest() == (
            "0b620f3fe613316860b9dae96dd3ff0106dafa9d5972ae5c9699538986184b0b"
        )
        assert Counter(m.sent_at.utcoffset() for m in parsed.messages) == {
            timedelta(hours=-7): 774, timedelta(hours=-8): 400,
        }
    for number, message in enumerate(parsed.messages, 1):
        assert message.identity_version == 2
        assert message.source.sha256 == EXPORT_SHA256
        assert message.source.document_id == meta.document_id
        assert message.source.record_locator == f"message:{number}/1174"
        assert message.source.source_type == "ofw_message_report"
        assert message.source.confidence is None
        assert message.source.extraction_method == "native"
        assert message.source_timezone_basis == "supplied"
    audit_compact_text(data, parsed.messages, meta.timezone)
    another = parse_ofw_message_report(data, "second-acquisition", report_timezone=meta.timezone)
    assert [m.message_id for m in another.messages] == [m.message_id for m in parsed.messages]


def assert_cross_report_records(records, older, newer):
    old_by_id = {m.message_id: m for m in older.messages}
    new_by_id = {m.message_id: m for m in newer.messages}
    assert len(records) == 1174
    assert set(old_by_id) <= set(new_by_id), "cross-report identity mismatch; verify timezone and layout"
    assert sum(len(r["source_occurrences"]) for r in records) == 1796
    for record in records:
        message_id = record["message_id"]
        expected = [new_by_id[message_id]]
        if message_id in old_by_id:
            expected.append(old_by_id[message_id])
        occurrences = record["source_occurrences"]
        assert record["occurrence_version"] == len(occurrences) == len(expected)
        assert len({o["occurrence_key"] for o in occurrences}) == len(expected)
        by_document = {o["source"]["document_id"]: o for o in occurrences}
        assert set(by_document) == {m.source.document_id for m in expected}
        for message in expected:
            occurrence = by_document[message.source.document_id]
            assert occurrence["source"] == message.source.model_dump(mode="python")
            assert occurrence["sent_at_raw"] == message.sent_at_raw
            assert occurrence["source_timezone"] == message.source_timezone
            assert occurrence["source_timezone_basis"] == message.source_timezone_basis
            assert occurrence["body"] == message.body
            assert occurrence["subject"] == message.subject
            assert occurrence["attachments"] == [a.model_dump(mode="python") for a in message.attachments]
            assert occurrence["read_receipts"] == [r.model_dump(mode="python") for r in message.read_receipts]
        assert record["sent_at"] == new_by_id[message_id].sent_at
        for receipt in record["read_receipts"]:
            views = [r.first_viewed_at for m in expected for r in m.read_receipts
                     if r.recipient_person_id == receipt["recipient_person_id"] and r.first_viewed_at is not None]
            assert receipt["first_viewed_at"] == (min(views) if views else None)


@pytest.mark.real_export
@pytest.mark.parametrize("reverse", [False, True])
@private_export_checks()
def test_oct30_overlap_bson_replay_and_original_occurrences(oct16_export, oct30_export, reverse):
    _, older = oct16_export
    _, newer = oct30_export
    reports = [newer, older] if reverse else [older, newer]
    collection = FakeCollection()
    results = []
    for report in reports:
        results.append(import_ofw_messages(collection, report))
        for key, record in collection.documents.items():
            collection.documents[key] = BSON.encode(record).decode(CodecOptions(tz_aware=True))
    assert [r.inserted_count for r in results] == ([1174, 0] if reverse else [622, 552])
    assert [r.occurrence_added_count for r in results] == ([1174, 622] if reverse else [622, 1174])
    assert_cross_report_records(list(collection.documents.values()), older, newer)
    for report in reports:
        replay = import_ofw_messages(collection, report)
        assert (replay.inserted_count, replay.occurrence_added_count) == (0, 0)
    assert_cross_report_records(list(collection.documents.values()), older, newer)
