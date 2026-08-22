import hashlib
from pathlib import Path

import pytest

from src.ofw_import import import_ofw_messages
from src.ofw_parser import parse_ofw_message_report
from tests.fakes import FakeCollection

PRIVATE_EXPORT = Path("tests/fixtures/private/OFW_Messages_Report.pdf")
EXPECTED_SHA256 = "f772295a7a53707ff03d694f10674b6bdd210cf7754472a2c6cbe2cd8f111b2c"


@pytest.mark.real_export
@pytest.mark.skipif(not PRIVATE_EXPORT.exists(), reason="private OFW export is not present")
def test_real_ofw_export_parser_and_import_acceptance():
    parsed = parse_ofw_message_report(
        PRIVATE_EXPORT.read_bytes(),
        document_id="ofw_messages_2026-07-11",
    )

    assert parsed.metadata.sha256 == EXPECTED_SHA256
    assert parsed.metadata.page_count == 1153
    assert parsed.metadata.timezone == "America/Vancouver"
    assert parsed.metadata.expected_message_count == 1047
    assert parsed.metadata.parsed_message_count == 1047
    assert len({message.message_id for message in parsed.messages}) == 1047
    ordered_id_digest = hashlib.sha256(
        "\n".join(message.message_id for message in parsed.messages).encode("utf-8")
    ).hexdigest()
    assert ordered_id_digest == (
        "80562e69906bc29166a45eac31cb0021d08b50ec478ac694d514b44eb95868fa"
    )
    assert parsed.messages[0].sent_at.isoformat() == "2024-06-19T14:37:00-07:00"
    assert parsed.messages[-1].sent_at.isoformat() == "2026-07-10T15:27:00-07:00"
    assert parsed.messages[3].source.page == 3
    assert all(
        message.source.page <= message.source.end_page <= 1153
        for message in parsed.messages
    )
    assert sum(len(message.attachments) for message in parsed.messages) == 280
    assert sum(bool(message.attachments) for message in parsed.messages) == 69
    assert sum(
        receipt.first_viewed_at is not None
        for message in parsed.messages
        for receipt in message.read_receipts
    ) == 1043
    assert sum(
        receipt.first_viewed_at_raw == "Never"
        for message in parsed.messages
        for receipt in message.read_receipts
    ) == 6
    assert all("See Attachments:" not in message.body for message in parsed.messages)
    assert parsed.messages[882].recipient_person_ids == [
        "person_lindsay_alene_mcclean",
        "person_laura_watson",
    ]
    assert parsed.messages[887].recipient_person_ids == [
        "person_lindsay_alene_mcclean",
        "person_sofia_rae_watson",
    ]

    collection = FakeCollection()
    first = import_ofw_messages(collection, parsed)
    second = import_ofw_messages(collection, parsed)
    assert (first.inserted_count, second.inserted_count) == (1047, 0)
    assert (first.occurrence_added_count, second.occurrence_added_count) == (1047, 0)
    assert len(collection.documents) == 1047
