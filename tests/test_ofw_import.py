from copy import deepcopy
from datetime import datetime, timezone

import pytest
from pymongo.errors import BulkWriteError

from src.ofw_import import OFWImportConflict, _source_occurrence, import_ofw_messages
from src.ofw_parser import parse_ofw_message_report_pages
from tests.fakes import FakeCollection
from tests.ofw_sample import (
    SAMPLE_OFW_EDMONTON_PAGES,
    SAMPLE_OFW_PAGES,
    SAMPLE_PERSON_IDS,
    SAMPLE_SOURCE_SHA256,
)


class OneShotDuplicateCollection(FakeCollection):
    def __init__(self):
        super().__init__()
        self.raised = False

    def bulk_write(self, operations, ordered=False):
        result = super().bulk_write(operations, ordered=ordered)
        if not self.raised:
            self.raised = True
            raise BulkWriteError({"writeErrors": [{"code": 11000}]})
        return result


class ReceiptRaceCollection(FakeCollection):
    def __init__(self):
        super().__init__()
        self.target_message_id = None
        self.concurrent_occurrence = None
        self.injected = False

    def inject_during_next_reconciliation(self, message_id, occurrence):
        self.target_message_id = message_id
        self.concurrent_occurrence = occurrence

    def find(self, query, projection=None):
        result = super().find(query, projection)
        is_reconciliation = projection and projection.get("occurrence_version")
        if is_reconciliation and self.concurrent_occurrence and not self.injected:
            for document in self.documents.values():
                if document.get("message_id") != self.target_message_id:
                    continue
                document["source_occurrences"].append(
                    deepcopy(self.concurrent_occurrence)
                )
                document["occurrence_version"] += 1
                self.injected = True
                break
        return result


def parsed_sample(
    document_id="sample-ofw-export",
    source_sha256=SAMPLE_SOURCE_SHA256,
):
    return parse_ofw_message_report_pages(
        pages=SAMPLE_OFW_PAGES,
        document_id=document_id,
        source_sha256=source_sha256,
        person_id_by_display_name=SAMPLE_PERSON_IDS,
    )


def test_import_is_idempotent_and_stores_bson_ready_datetimes():
    collection = FakeCollection()
    parsed = parsed_sample()

    first = import_ofw_messages(collection, parsed)
    second = import_ofw_messages(collection, parsed)

    assert first.inserted_count == 2
    assert first.existing_count == 0
    assert first.occurrence_added_count == 2
    assert second.inserted_count == 0
    assert second.existing_count == 2
    assert second.occurrence_added_count == 0
    assert len(collection.documents) == 2
    assert all(isinstance(document["sent_at"], datetime) for document in collection.documents.values())
    assert all(
        len(document["source_occurrences"]) == 1
        for document in collection.documents.values()
    )
    assert collection.indexes[0][1]["unique"] is True
    assert collection.indexes[0][1]["name"] == "uq_case_id_message_id"


def test_import_preserves_provenance_across_overlapping_exports():
    collection = FakeCollection()
    first = parsed_sample(document_id="export-a", source_sha256="a" * 64)
    second = parsed_sample(document_id="export-b", source_sha256="b" * 64)

    import_ofw_messages(collection, first)
    summary = import_ofw_messages(collection, second)

    assert summary.inserted_count == 0
    assert summary.existing_count == 2
    assert summary.occurrence_added_count == 2
    assert all(
        {occurrence["source"]["sha256"] for occurrence in document["source_occurrences"]}
        == {"a" * 64, "b" * 64}
        for document in collection.documents.values()
    )
    assert all(
        {occurrence["source_timezone"] for occurrence in document["source_occurrences"]}
        == {"America/Vancouver"}
        for document in collection.documents.values()
    )


def test_import_preserves_timezone_for_each_source_occurrence():
    collection = FakeCollection()
    vancouver = parsed_sample(document_id="vancouver", source_sha256="a" * 64)
    edmonton = parse_ofw_message_report_pages(
        pages=SAMPLE_OFW_EDMONTON_PAGES,
        document_id="edmonton",
        source_sha256="b" * 64,
        person_id_by_display_name=SAMPLE_PERSON_IDS,
    )

    import_ofw_messages(collection, vancouver)
    import_ofw_messages(collection, edmonton)

    assert all(
        {occurrence["source_timezone"] for occurrence in document["source_occurrences"]}
        == {"America/Vancouver", "America/Edmonton"}
        for document in collection.documents.values()
    )


def test_import_replay_uses_source_identity_after_bson_datetime_round_trip():
    collection = FakeCollection()
    parsed = parsed_sample()
    import_ofw_messages(collection, parsed)
    for document in collection.documents.values():
        for occurrence in document["source_occurrences"]:
            for receipt in occurrence["read_receipts"]:
                if receipt["first_viewed_at"] is not None:
                    receipt["first_viewed_at"] = receipt["first_viewed_at"].astimezone(
                        timezone.utc
                    )

    summary = import_ofw_messages(collection, parsed)

    assert summary.inserted_count == 0
    assert summary.occurrence_added_count == 0


def test_later_export_promotes_never_viewed_to_earliest_view_timestamp():
    collection = FakeCollection()
    first = parsed_sample(document_id="export-a", source_sha256="a" * 64)
    updated_pages = [
        page.replace(
            "Parent Alpha (First Viewed: Never)",
            "Parent Alpha (First Viewed: 01/31/2026 9:00 AM)",
        )
        for page in SAMPLE_OFW_PAGES
    ]
    second = parse_ofw_message_report_pages(
        pages=updated_pages,
        document_id="export-b",
        source_sha256="b" * 64,
        person_id_by_display_name=SAMPLE_PERSON_IDS,
    )

    import_ofw_messages(collection, first)
    summary = import_ofw_messages(collection, second)
    stored = collection.find_one(
        {"case_id": second.messages[1].case_id, "message_id": second.messages[1].message_id}
    )

    assert summary.inserted_count == 0
    assert summary.occurrence_added_count == 2
    assert stored["read_receipts"][0]["first_viewed_at"].isoformat() == (
        "2026-01-31T09:00:00-08:00"
    )
    assert stored["read_receipts"][0]["first_viewed_at_raw"] == (
        "01/31/2026 9:00 AM"
    )
    assert stored["read_at"] is None


def test_concurrent_identical_import_reconciles_duplicate_key_race():
    collection = OneShotDuplicateCollection()
    parsed = parsed_sample()

    summary = import_ofw_messages(collection, parsed)

    assert collection.raised is True
    assert summary.inserted_count == 0
    assert len(collection.documents) == 2
    assert all(
        len(document["source_occurrences"]) == 1
        for document in collection.documents.values()
    )


def test_receipt_reconciliation_retries_when_occurrences_change_concurrently():
    collection = ReceiptRaceCollection()
    initial = parsed_sample(document_id="export-a", source_sha256="a" * 64)
    later_pages = [
        page.replace(
            "Parent Alpha (First Viewed: Never)",
            "Parent Alpha (First Viewed: 01/31/2026 9:00 AM)",
        )
        for page in SAMPLE_OFW_PAGES
    ]
    earlier_pages = [
        page.replace(
            "Parent Alpha (First Viewed: Never)",
            "Parent Alpha (First Viewed: 01/30/2026 4:00 PM)",
        )
        for page in SAMPLE_OFW_PAGES
    ]
    later = parse_ofw_message_report_pages(
        later_pages,
        document_id="export-b",
        source_sha256="b" * 64,
        person_id_by_display_name=SAMPLE_PERSON_IDS,
    )
    concurrent = parse_ofw_message_report_pages(
        earlier_pages,
        document_id="export-c",
        source_sha256="c" * 64,
        person_id_by_display_name=SAMPLE_PERSON_IDS,
    )
    target = later.messages[1]

    import_ofw_messages(collection, initial)
    collection.inject_during_next_reconciliation(
        target.message_id,
        _source_occurrence(concurrent.messages[1]),
    )
    import_ofw_messages(collection, later)
    stored = collection.find_one(
        {"case_id": target.case_id, "message_id": target.message_id}
    )

    assert collection.injected is True
    assert stored["occurrence_version"] == 3
    assert stored["read_receipts"][0]["first_viewed_at"].isoformat() == (
        "2026-01-30T16:00:00-08:00"
    )


def test_import_rejects_an_existing_id_with_different_content():
    collection = FakeCollection()
    parsed = parsed_sample()
    import_ofw_messages(collection, parsed)
    first_document = next(iter(collection.documents.values()))
    first_document["content_sha256"] = "f" * 64

    with pytest.raises(OFWImportConflict, match="different content"):
        import_ofw_messages(collection, parsed)
