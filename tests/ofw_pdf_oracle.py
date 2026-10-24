"""Independent layout checks for the pinned October export; no private text stored.

Unlike the production text/regex parser, this oracle locates native PDF lines by
coordinates. Its geometry is specific to this fixture, not a general OFW parser.
Only hashes of compared text are exposed on assertion failure.
"""

import hashlib
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import fitz

from src.case_intelligence import PERSON_ID_BY_DISPLAY_NAME


def _normalized(text):
    return " ".join(text.split())


def _assert_text_equal(actual, expected, label):
    # Avoid leaking private message text through pytest's assertion rewriting.
    actual_digest = hashlib.sha256(_normalized(actual).encode()).hexdigest()
    expected_digest = hashlib.sha256(_normalized(expected).encode()).hexdigest()
    assert actual_digest == expected_digest, label


def _timestamp(raw):
    match = re.fullmatch(r"(\d{2}/\d{2}/\d{4})\s*(\d{1,2}:\d{2})\s*(AM|PM)", raw)
    assert match, "unrecognized source timestamp"
    value = " ".join(match.groups())
    return value, datetime.strptime(value, "%m/%d/%Y %I:%M %p").replace(
        tzinfo=ZoneInfo("America/Vancouver")
    )


def assert_oct16_layout_matches(data, messages):
    """Check all primary headers, bodies, attachments and page ranges."""
    rows = []
    with fitz.open(stream=data, filetype="pdf") as report:
        for page_number, page in enumerate(report, 1):
            page_rows = []
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    x, y, _, _ = line["bbox"]
                    text = "".join(span["text"] for span in line["spans"]).strip()
                    # Footer is below 740 points on this report's letter pages.
                    if text and y < 740:
                        page_rows.append((page_number, round(y, 1), x, text))
            rows.extend(sorted(page_rows))

    markers = [
        i for i, row in enumerate(rows)
        if re.fullmatch(r"Message \d+ of 622", row[3])
    ]
    assert len(markers) == len(messages) == 622
    for number, (start, message) in enumerate(zip(markers, messages), 1):
        assert rows[start][3] == f"Message {number} of 622"
        stop = markers[number] if number < len(markers) else len(rows)
        block = rows[start + 1:stop]
        # Quoted thread headers are indented; primary headers start at x=51.75.
        quoted = next(
            (i for i, row in enumerate(block) if row[3] == "Sent:" and row[2] > 90),
            len(block),
        )
        primary = block[:quoted]
        assert (message.source.page, message.source.end_page) == (
            rows[start][0], primary[-1][0]
        ), f"message {number}: source-page range"

        fields = {}
        header_rows = {}
        for row in primary:
            if row[2] < 60 and row[3] in ("Sent:", "From:", "To:", "Subject:"):
                values = [
                    item[3] for item in primary
                    if item[0] == row[0] and abs(item[1] - row[1]) < 2.5
                    and item[2] > 100
                ]
                fields[row[3]] = _normalized(" ".join(values))
                header_rows[row[3]] = row
        assert set(fields) == {"Sent:", "From:", "To:", "Subject:"}
        sent_raw, sent_at = _timestamp(fields["Sent:"])
        _assert_text_equal(message.sent_at_raw, sent_raw, f"message {number}: raw sent time")
        assert message.sent_at == sent_at, f"message {number}: sent time"
        assert message.sent_at.utcoffset() == sent_at.utcoffset()
        assert message.sender_person_id == PERSON_ID_BY_DISPLAY_NAME[fields["From:"].casefold()]
        _assert_text_equal(message.subject, fields["Subject:"], f"message {number}: subject")

        recipient = re.fullmatch(r"(.*?)\s*\(First\s*Viewed:\s*(.*?)\)", fields["To:"])
        assert recipient, f"message {number}: receipt header"
        person_id = PERSON_ID_BY_DISPLAY_NAME[recipient[1].strip().casefold()]
        viewed_raw, viewed_at = _timestamp(recipient[2])
        assert message.recipient_person_ids == [person_id]
        assert len(message.read_receipts) == 1
        receipt = message.read_receipts[0]
        assert receipt.recipient_person_id == person_id
        assert receipt.first_viewed_at == viewed_at
        assert receipt.first_viewed_at.utcoffset() == viewed_at.utcoffset()
        _assert_text_equal(receipt.first_viewed_at_raw, viewed_raw, f"message {number}: raw receipt")
        assert message.read_at == viewed_at

        subject_row = header_rows["Subject:"]
        body_rows = [row for row in primary if (row[0], row[1]) > (subject_row[0], subject_row[1] + 3)]
        text = _normalized(" ".join(row[3] for row in body_rows))
        body, separator, attachment_text = text.partition("See Attachments:")
        _assert_text_equal(message.body, body, f"message {number}: body")
        expected_attachments = []
        if separator:
            for item in re.split(r"(?<=\)),\s*", attachment_text.strip()):
                filename, _, size = item.rpartition(" (")
                assert filename and size.endswith(")"), f"message {number}: attachment"
                expected_attachments.append((filename, size[:-1]))
        assert len(message.attachments) == len(expected_attachments)
        for actual, (filename, size) in zip(message.attachments, expected_attachments):
            _assert_text_equal(actual.raw_filename, filename, f"message {number}: attachment filename")
            _assert_text_equal(actual.display_size, size, f"message {number}: attachment size")
