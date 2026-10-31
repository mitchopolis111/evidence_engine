from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier

import pytest
from pymongo.errors import DuplicateKeyError

from src.ofw_import import OFWImportConflict, _source_occurrence, import_ofw_messages
from src.ofw_parser import parse_ofw_message_report_pages
from src.ofw_parser import parse_ofw_message_report
from tests.test_ofw_compact import compact_pdf
from tests.ofw_mongo_server import isolated_mongo, mongo_collection  # noqa: F401
from tests.ofw_private_checks import private_export_checks
from tests.ofw_sample import SAMPLE_OFW_PAGES, SAMPLE_PERSON_IDS
from tests.test_ofw_import import parsed_sample
from tests.test_ofw_oct16_export import oct16_export  # noqa: F401

pytestmark = pytest.mark.mongodb


def test_live_source_record_rejects_reinterpreted_timezone(mongo_collection):
    data = compact_pdf()
    reports = [parse_ofw_message_report(data, f"acquisition-{zone}", report_timezone=zone,
                                       person_id_by_display_name=SAMPLE_PERSON_IDS)
               for zone in ["America/Vancouver", "America/Edmonton"]]
    import_ofw_messages(mongo_collection, reports[0])
    before = list(mongo_collection.find({}))
    with pytest.raises(OFWImportConflict, match="source record"):
        import_ofw_messages(mongo_collection, reports[1])
    assert list(mongo_collection.find({})) == before
    index = mongo_collection.index_information()["uq_case_source_record"]
    assert index["unique"]


def test_concurrent_conflicting_timezone_cannot_duplicate_source_record(mongo_collection):
    data = compact_pdf()
    reports = [parse_ofw_message_report(data, f"acquisition-{zone}", report_timezone=zone,
                                       person_id_by_display_name=SAMPLE_PERSON_IDS)
               for zone in ["America/Vancouver", "America/Edmonton"]]
    for report in reports:
        report.messages = report.messages[:1]
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(import_ofw_messages, SynchronizedReadCollection(mongo_collection, barrier), report)
                   for report in reports]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result(timeout=45))
            except OFWImportConflict:
                outcomes.append("conflict")
    assert outcomes.count("conflict") == 1
    assert mongo_collection.count_documents({}) == 1
    stored = mongo_collection.find_one({})
    assert len(stored["source_occurrences"]) == stored["occurrence_version"] == 1


class SynchronizedReadCollection:
    """Force each caller to read the same pre-write state; writes remain real."""

    def __init__(self, collection, barrier):
        self.collection = collection
        self.barrier = barrier
        self.waited = False

    def __getattr__(self, name):
        return getattr(self.collection, name)

    def find(self, query, projection=None):
        documents = list(self.collection.find(query, projection))
        if not self.waited and projection and projection.get("content_sha256"):
            self.waited = True
            self.barrier.wait(timeout=20)
        return documents


def concurrent_imports(collection, reports):
    barrier = Barrier(len(reports))
    with ThreadPoolExecutor(max_workers=len(reports)) as pool:
        futures = [
            pool.submit(import_ofw_messages, SynchronizedReadCollection(collection, barrier), report)
            for report in reports
        ]
        return [future.result(timeout=45) for future in futures]


def assert_occurrences(collection, expected_messages, occurrences_per_message):
    assert collection.count_documents({}) == expected_messages
    for document in collection.find({}):
        occurrences = document["source_occurrences"]
        assert len(occurrences) == len({o["occurrence_key"] for o in occurrences}) == occurrences_per_message
        assert document["occurrence_version"] == occurrences_per_message


def test_real_mongodb_sequential_replay_and_unique_index(mongo_collection):
    parsed = parsed_sample()
    first = import_ofw_messages(mongo_collection, parsed)
    replay = import_ofw_messages(mongo_collection, parsed)
    assert (first.inserted_count, first.occurrence_added_count) == (2, 2)
    assert (replay.inserted_count, replay.occurrence_added_count) == (0, 0)
    assert_occurrences(mongo_collection, 2, 1)
    index = mongo_collection.index_information()["uq_case_id_message_id"]
    assert index["unique"] and index["key"] == [("case_id", 1), ("message_id", 1)]
    duplicate = mongo_collection.find_one({})
    duplicate.pop("_id")
    with pytest.raises(DuplicateKeyError):
        mongo_collection.insert_one(duplicate)


@pytest.mark.parametrize("legacy_kind", ["unkeyed_occurrences", "message_only"])
def test_legacy_records_replay_without_rewriting_original_provenance(mongo_collection, legacy_kind):
    parsed = parsed_sample(document_id="legacy")
    for message in parsed.messages:
        record = message.model_dump(mode="python")
        if legacy_kind == "unkeyed_occurrences":
            occurrence = _source_occurrence(message)
            occurrence.pop("occurrence_key")
            record.update(source_occurrences=[occurrence], occurrence_version=1)
        mongo_collection.insert_one(record)
    first = import_ofw_messages(mongo_collection, parsed)
    assert first.inserted_count == 0
    assert first.occurrence_added_count == (0 if legacy_kind == "unkeyed_occurrences" else 2)
    second = parsed_sample(document_id="new-source", source_sha256="b" * 64)
    added = import_ofw_messages(mongo_collection, second)
    assert (added.inserted_count, added.occurrence_added_count) == (0, 2)
    for report in (parsed, second):
        replay = import_ofw_messages(mongo_collection, report)
        assert (replay.inserted_count, replay.occurrence_added_count) == (0, 0)
    for document in mongo_collection.find({}):
        assert document["source"]["document_id"] == "legacy"
        assert document["occurrence_version"] == len(document["source_occurrences"]) == 2
        assert {o["source"]["document_id"] for o in document["source_occurrences"]} == {"legacy", "new-source"}


@pytest.mark.parametrize("workers", [2, 8])
def test_concurrent_same_export_counts_only_actual_writes(mongo_collection, workers):
    reports = [parsed_sample() for _ in range(workers)]
    results = concurrent_imports(mongo_collection, reports)
    assert_occurrences(mongo_collection, 2, 1)
    assert sum(r.inserted_count for r in results) == 2
    assert sum(r.occurrence_added_count for r in results) == 2


def test_concurrent_distinct_sources_preserve_every_occurrence(mongo_collection):
    reports = [parsed_sample(document_id=f"source-{i}") for i in range(8)]
    results = concurrent_imports(mongo_collection, reports)
    assert_occurrences(mongo_collection, 2, 8)
    assert sum(r.inserted_count for r in results) == 2
    assert sum(r.occurrence_added_count for r in results) == 16
    for document in mongo_collection.find({}):
        assert {o["source"]["document_id"] for o in document["source_occurrences"]} == {
            f"source-{i}" for i in range(8)
        }


def test_concurrent_replay_deduplicates_occurrence_identity_not_entire_object(mongo_collection):
    first = parsed_sample()
    second = deepcopy(first)
    # Simulate an earlier parser's confidence field for the same source identity.
    for message in second.messages:
        message.source.confidence = 1.0
    results = concurrent_imports(mongo_collection, [first, second])
    assert_occurrences(mongo_collection, 2, 1)
    assert sum(result.occurrence_added_count for result in results) == 2


def test_concurrent_receipts_converge_to_earliest_view_and_preserve_sources(mongo_collection):
    initial = parsed_sample(document_id="initial")
    import_ofw_messages(mongo_collection, initial)
    reports = []
    for document_id, viewed_at in [("later", "01/31/2026 9:00 AM"), ("earlier", "01/30/2026 4:00 PM")]:
        pages = [page.replace("First Viewed: Never", f"First Viewed: {viewed_at}") for page in SAMPLE_OFW_PAGES]
        reports.append(parse_ofw_message_report_pages(
            pages, document_id=document_id, source_sha256="b" * 64,
            person_id_by_display_name=SAMPLE_PERSON_IDS,
        ))
    results = concurrent_imports(mongo_collection, reports)
    assert sum(result.inserted_count for result in results) == 0
    assert sum(result.occurrence_added_count for result in results) == 4
    assert_occurrences(mongo_collection, 2, 3)
    target = mongo_collection.find_one({"message_id": initial.messages[1].message_id})
    assert target["read_receipts"][0]["first_viewed_at"].isoformat() == "2026-01-31T00:00:00+00:00"
    assert target["read_receipts"][0]["first_viewed_at_raw"] == "01/30/2026 4:00 PM"
    assert target["read_at"] is None  # Multiple recipients retain separate receipts.


def test_conflicting_content_race_fails_without_mixing_provenance(mongo_collection):
    first = parsed_sample(document_id="first")
    first.messages = first.messages[:1]
    second = deepcopy(first)
    second.messages[0].source.document_id = "conflicting"
    second.messages[0].body = "Synthetic conflicting body"
    second.messages[0].content_sha256 = "f" * 64
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(import_ofw_messages, SynchronizedReadCollection(mongo_collection, barrier), report)
            for report in (first, second)
        ]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result(timeout=45))
            except OFWImportConflict:
                outcomes.append("conflict")
    assert outcomes.count("conflict") == 1
    assert_occurrences(mongo_collection, 1, 1)
    stored = mongo_collection.find_one({})
    winner = "conflicting" if stored["content_sha256"] == "f" * 64 else "first"
    assert stored["source_occurrences"][0]["source"]["document_id"] == winner


@pytest.mark.real_export
@private_export_checks()
def test_oct16_real_mongodb_replay_and_concurrent_imports(mongo_collection, oct16_export):
    _, parsed = oct16_export
    first = import_ofw_messages(mongo_collection, parsed)
    assert (first.inserted_count, first.occurrence_added_count) == (622, 622)
    replay = import_ofw_messages(mongo_collection, parsed)
    assert (replay.inserted_count, replay.occurrence_added_count) == (0, 0)
    # Fresh database collection: eight synchronized imports of the actual report.
    concurrent = mongo_collection.database.concurrent_messages
    results = concurrent_imports(concurrent, [parsed] * 8)
    assert_occurrences(concurrent, 622, 1)
    assert sum(r.inserted_count for r in results) == 622
    assert sum(r.occurrence_added_count for r in results) == 622
    copies = []
    for i in range(4):
        report = parsed.model_copy(deep=True)
        report.metadata.document_id = f"separate-copy-{i}"
        for message in report.messages:
            message.source.document_id = report.metadata.document_id
        copies.append(report)
    results = concurrent_imports(concurrent, copies)
    assert sum(r.inserted_count for r in results) == 0
    assert sum(r.occurrence_added_count for r in results) == 2488
    assert_occurrences(concurrent, 622, 5)
    replays = concurrent_imports(concurrent, copies * 2)
    assert sum(result.inserted_count for result in replays) == 0
    assert sum(result.occurrence_added_count for result in replays) == 0
    assert_occurrences(concurrent, 622, 5)
    by_id = {m.message_id: m for m in parsed.messages}
    for stored in concurrent.find({}):
        message = by_id[stored["message_id"]]
        assert stored["content_sha256"] == message.content_sha256
        assert stored["sent_at"] == message.sent_at
        assert stored["read_receipts"] == [r.model_dump(mode="python") for r in message.read_receipts]
        for occurrence in stored["source_occurrences"]:
            assert occurrence["source"]["sha256"] == parsed.metadata.sha256
            assert occurrence["source"]["page"] == message.source.page
            assert occurrence["source"]["end_page"] == message.source.end_page
