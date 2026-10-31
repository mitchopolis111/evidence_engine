"""Independent sorted-text audit of the pinned compact report.

Production reads native PDF coordinates. This oracle instead splits sorted text
at report markers and table labels, comparing normalized values without sharing
production extraction or fingerprint code. Run only inside private checks.
"""

import re
from datetime import datetime
from zoneinfo import ZoneInfo

import fitz

from src.case_intelligence import PERSON_ID_BY_DISPLAY_NAME


def audit_compact_text(data, messages, timezone_name):
    lines = []
    with fitz.open(stream=data, filetype="pdf") as pdf:
        for page_number, page in enumerate(pdf, 1):
            for line in page.get_text("text", sort=True).splitlines():
                if line.strip() and not re.fullmatch(r"\s*Page \d+ of \d+\s*", line):
                    lines.append((page_number, line.strip()))
    starts = [i for i, (_, line) in enumerate(lines) if re.fullmatch(r"Message \d+ of 1174", line)]
    assert len(starts) == len(messages) == 1174
    normalize = lambda text: " ".join(text.split())

    def timestamp(value):
        match = re.fullmatch(r"(\d{2}/\d{2}/\d{4})\s*(\d{1,2}:\d{2})\s*(AM|PM)", value)
        assert match, "timestamp syntax"
        raw = " ".join(match.groups())
        return raw, datetime.strptime(raw, "%m/%d/%Y %I:%M %p").replace(tzinfo=ZoneInfo(timezone_name))

    for index, (start, message) in enumerate(zip(starts, messages)):
        stop = starts[index + 1] if index + 1 < len(starts) else len(lines)
        block = lines[start + 1:stop]
        assert lines[start][1] == f"Message {index + 1} of 1174"
        assert (message.source.page, message.source.end_page) == (lines[start][0], block[-1][0])
        sent = re.fullmatch(r"SENT\s+(.*?)\s+FROM\s+(.*)", block[0][1])
        assert sent, "sent/from table row"
        raw, expected = timestamp(sent[1])
        assert message.sent_at_raw == raw and message.sent_at == expected
        assert message.sent_at.utcoffset() == expected.utcoffset()
        assert message.sender_person_id == PERSON_ID_BY_DISPLAY_NAME[normalize(sent[2]).casefold()]
        subject_index = next(i for i, (_, text) in enumerate(block) if text.startswith("SUBJECT"))
        to_text = " ".join(text for _, text in block[1:subject_index])
        assert to_text.startswith("TO ")
        receipts = list(re.finditer(r"(.*?)\s*\(First\s*Viewed:\s*(.*?)\)", to_text[3:]))
        assert len(receipts) == len(message.read_receipts)
        for receipt, actual in zip(receipts, message.read_receipts):
            assert actual.recipient_person_id == PERSON_ID_BY_DISPLAY_NAME[normalize(receipt[1]).casefold()]
            value = receipt[2].strip()
            if value.casefold() in {"never", "not viewed"}:
                assert actual.first_viewed_at is None and actual.first_viewed_at_raw == value
            else:
                raw, expected = timestamp(value)
                assert actual.first_viewed_at == expected and actual.first_viewed_at_raw == raw
                assert actual.first_viewed_at.utcoffset() == expected.utcoffset()
        assert message.recipient_person_ids == [r.recipient_person_id for r in message.read_receipts]
        expected_read = message.read_receipts[0].first_viewed_at if len(receipts) == 1 else None
        assert message.read_at == expected_read
        subject = block[subject_index][1].removeprefix("SUBJECT").strip()
        assert normalize(message.subject) == normalize(subject), f"message {index+1}: subject"
        body = normalize(" ".join(text for _, text in block[subject_index + 1:]))
        body, separator, attachments = body.partition("See Attachments:")
        assert normalize(message.body) == normalize(body), f"message {index+1}: body"
        expected_attachments = []
        if separator:
            for item in re.split(r"(?<=\)),\s*", attachments.strip()):
                filename, _, size = item.rpartition(" (")
                assert filename and size.endswith(")")
                expected_attachments.append((filename, size[:-1]))
        assert [(normalize(a.raw_filename), a.display_size) for a in message.attachments] == expected_attachments
