from __future__ import annotations

from pydantic import BaseModel
from pymongo import UpdateOne
from pymongo.errors import BulkWriteError

from .ofw_parser import OFWParseResult
from .storage_contracts import ensure_unique_key_index

OFW_MESSAGE_KEY_FIELDS = ("case_id", "message_id")


class OFWImportConflict(ValueError):
    pass


class OFWImportSummary(BaseModel):
    source_sha256: str
    parsed_count: int
    inserted_count: int
    existing_count: int
    occurrence_added_count: int


def _source_occurrence(message) -> dict:
    occurrence = {
        "source": message.source.model_dump(mode="python"),
        "subject": message.subject,
        "body": message.body,
        "source_timezone": message.source_timezone,
        "source_timezone_basis": message.source_timezone_basis,
        "sent_at_raw": message.sent_at_raw,
        "read_receipts": [
            receipt.model_dump(mode="python") for receipt in message.read_receipts
        ],
        "attachments": [
            attachment.model_dump(mode="python") for attachment in message.attachments
        ],
        "report_message_number": message.report_message_number,
        "report_message_total": message.report_message_total,
    }
    occurrence["occurrence_key"] = _occurrence_key(occurrence)
    occurrence["source_record_key"] = _source_record_key(occurrence)
    return occurrence


def _source_record_key(occurrence: dict) -> str:
    source = occurrence["source"]
    locator = source.get("record_locator") or f"page:{source.get('page')}"
    return f"{source['sha256']}:{source['source_type']}:{locator}"


def _occurrence_key(occurrence: dict) -> str:
    source = occurrence["source"]
    locator = source.get("record_locator") or f"page:{source.get('page')}"
    return (
        f"{source['sha256']}:{source['document_id']}:"
        f"{source['source_type']}:{locator}"
    )


def _canonical_read_receipts(document: dict) -> list[dict]:
    receipt_sets = [
        occurrence.get("read_receipts", [])
        for occurrence in document.get("source_occurrences", [])
    ]
    if not receipt_sets:
        receipt_sets = [document.get("read_receipts", [])]
    selected_by_recipient: dict[str, dict] = {}
    for receipts in receipt_sets:
        for receipt in receipts:
            recipient_id = receipt["recipient_person_id"]
            previous = selected_by_recipient.get(recipient_id)
            if previous is None:
                selected_by_recipient[recipient_id] = receipt
                continue
            previous_at = previous.get("first_viewed_at")
            incoming_at = receipt.get("first_viewed_at")
            if previous_at is None and incoming_at is not None:
                selected_by_recipient[recipient_id] = receipt
            elif (
                previous_at is not None
                and incoming_at is not None
                and incoming_at < previous_at
            ):
                selected_by_recipient[recipient_id] = receipt

    merged: list[dict] = []
    for recipient_id in document["recipient_person_ids"]:
        merged.append(
            selected_by_recipient.get(
                recipient_id,
                {
                    "recipient_person_id": recipient_id,
                    "first_viewed_at": None,
                    "first_viewed_at_raw": None,
                },
            )
        )
    return merged


def _reconcile_read_receipts(collection, case_id: str, message_ids: list[str]) -> None:
    for _ in range(5):
        documents = list(
            collection.find(
                {"case_id": case_id, "message_id": {"$in": message_ids}},
                {
                    "_id": 0,
                    "case_id": 1,
                    "message_id": 1,
                    "recipient_person_ids": 1,
                    "read_receipts": 1,
                    "source_occurrences": 1,
                    "occurrence_version": 1,
                },
            )
        )
        operations = []
        for document in documents:
            receipts = _canonical_read_receipts(document)
            operations.append(
                UpdateOne(
                    {
                        "case_id": document["case_id"],
                        "message_id": document["message_id"],
                        "occurrence_version": document.get("occurrence_version"),
                    },
                    {
                        "$set": {
                            "read_receipts": receipts,
                            "read_at": (
                                receipts[0]["first_viewed_at"]
                                if len(document["recipient_person_ids"]) == 1
                                else None
                            ),
                        }
                    },
                )
            )
        if not operations:
            return
        result = collection.bulk_write(operations, ordered=False)
        if result.matched_count == len(operations):
            return
    raise OFWImportConflict("receipt reconciliation did not reach a stable version")


def _is_duplicate_key_error(exc: BulkWriteError) -> bool:
    details = exc.details or {}
    write_errors = details.get("writeErrors", [])
    return (
        bool(write_errors)
        and not details.get("writeConcernErrors")
        and all(error.get("code") == 11000 for error in write_errors)
    )


def import_ofw_messages(
    collection,
    parsed: OFWParseResult,
) -> OFWImportSummary:
    """Idempotently import one validated OFW message report into a Mongo collection."""
    messages = parsed.messages
    if not messages:
        return OFWImportSummary(
            source_sha256=parsed.metadata.sha256,
            parsed_count=0,
            inserted_count=0,
            existing_count=0,
            occurrence_added_count=0,
        )

    case_ids = {message.case_id for message in messages}
    if len(case_ids) != 1:
        raise OFWImportConflict("one OFW import cannot span multiple cases")
    case_id = next(iter(case_ids))

    if any(message.identity_version != 2 for message in messages):
        raise OFWImportConflict("identity version 2 requires reparsing original reports")
    if collection.find_one({"case_id": case_id, "identity_version": {"$ne": 2}}):
        raise OFWImportConflict(
            "legacy identity version present; reparse original reports into a fresh collection"
        )

    ensure_unique_key_index(collection, OFW_MESSAGE_KEY_FIELDS)
    # One physical PDF record cannot become two canonical messages, even when
    # different callers supply conflicting timezones or acquisition IDs.
    collection.create_index(
        [("case_id", 1), ("source_occurrences.source_record_key", 1)],
        unique=True, name="uq_case_source_record",
        partialFilterExpression={"source_occurrences.source_record_key": {"$exists": True}},
    )
    source_ids = {_source_record_key(_source_occurrence(m)): m.message_id for m in messages}
    for stored in collection.find(
        {"case_id": case_id, "source_occurrences.source_record_key": {"$in": list(source_ids)}},
        {"_id": 0, "message_id": 1, "source_occurrences": 1},
    ):
        for occurrence in stored.get("source_occurrences", []):
            expected_id = source_ids.get(_source_record_key(occurrence))
            if expected_id is not None and expected_id != stored["message_id"]:
                raise OFWImportConflict("source record already has a different identity; verify timezone and rebuild")
    message_by_id = {message.message_id: message for message in messages}
    if len(message_by_id) != len(messages):
        raise OFWImportConflict("parsed report contains duplicate message IDs")

    existing_documents = collection.find(
        {"case_id": case_id, "message_id": {"$in": list(message_by_id)}},
        {
            "_id": 0,
            "message_id": 1,
            "content_sha256": 1,
            "source_occurrences": 1,
        },
    )
    known_occurrences: dict[str, set[str]] = {}
    for existing in existing_documents:
        message_id = existing["message_id"]
        parsed_message = message_by_id.get(message_id)
        if parsed_message is None:
            continue
        if existing.get("content_sha256") != parsed_message.content_sha256:
            raise OFWImportConflict(
                f"message_id already exists with different content: {message_id}"
            )
        known_occurrences[message_id] = {
            occurrence.get("occurrence_key") or _occurrence_key(occurrence)
            for occurrence in existing.get("source_occurrences", [])
        }

    insert_operations = []
    occurrence_operations = []
    for message in messages:
        occurrence = _source_occurrence(message)
        occurrence_key = occurrence["occurrence_key"]
        occurrence_is_new = occurrence_key not in known_occurrences.get(
            message.message_id,
            set(),
        )
        payload = message.model_dump(mode="python")
        # Insert the first provenance record with the message, atomically.
        payload["source_occurrences"] = [occurrence]
        payload["occurrence_version"] = 1
        content_key = {
            "case_id": message.case_id,
            "message_id": message.message_id,
            "content_sha256": message.content_sha256,
        }
        insert_operations.append(UpdateOne(content_key, {"$setOnInsert": payload}, upsert=True))
        if occurrence_is_new:
            # A stale pre-read must not increment the version or count a replay.
            # The unique content guard also prevents attaching conflicting evidence.
            occurrence_operations.append(
                UpdateOne(
                    {**content_key, "source_occurrences.occurrence_key": {"$ne": occurrence_key}},
                    {
                        "$addToSet": {"source_occurrences": occurrence},
                        "$inc": {"occurrence_version": 1},
                    },
                )
            )

    try:
        result = collection.bulk_write(insert_operations, ordered=False)
        inserted_count = result.upserted_count
    except BulkWriteError as exc:
        if not _is_duplicate_key_error(exc):
            raise
        # An unordered bulk can partially succeed. Keep its actual insert count;
        # rerunning the whole import would lose those acknowledged writes.
        inserted_count = exc.details.get("nUpserted", 0)
        stored = list(collection.find(
            {"case_id": case_id, "message_id": {"$in": list(message_by_id)}},
            {"_id": 0, "message_id": 1, "content_sha256": 1},
        ))
        if len(stored) != len(message_by_id):
            raise OFWImportConflict("concurrent import did not persist every message") from None
        for document in stored:
            if document.get("content_sha256") != message_by_id[document["message_id"]].content_sha256:
                raise OFWImportConflict("message_id already exists with different content") from None

    occurrence_added_count = inserted_count
    if occurrence_operations:
        added = collection.bulk_write(occurrence_operations, ordered=False)
        occurrence_added_count += added.modified_count
    _reconcile_read_receipts(collection, case_id, list(message_by_id))

    return OFWImportSummary(
        source_sha256=parsed.metadata.sha256,
        parsed_count=len(messages),
        inserted_count=inserted_count,
        existing_count=len(messages) - inserted_count,
        occurrence_added_count=occurrence_added_count,
    )
