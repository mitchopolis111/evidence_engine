"""Native compact OFW tables, whose reports omit timezone/cover metadata.

Geometry separates wrapped header values from the body. The original PDF is
read only; a caller must supply the display timezone, recorded as supplied.
"""

import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .case_intelligence import PERSON_ID_BY_DISPLAY_NAME, sha256_bytes
from .ofw_parser import (
    OFWParseError, OFWParseResult, OFWReportMetadata, _normalize_name, _parse_message_block,
)


def parse_compact_report(report, data, document_id, case_id, person_ids, report_timezone):
    if not report_timezone:
        raise OFWParseError("compact OFW report requires explicit report_timezone; PDF does not declare one")
    try:
        timezone = ZoneInfo(report_timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise OFWParseError("unknown OFW report timezone") from exc
    names = {_normalize_name(k): v for k, v in PERSON_ID_BY_DISPLAY_NAME.items()}
    names.update({_normalize_name(k): v for k, v in (person_ids or {}).items()})
    rows = []
    for page_number, page in enumerate(report, 1):
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                x, y, _, bottom = line["bbox"]
                text = "".join(span["text"] for span in line["spans"]).strip()
                if not text:
                    continue
                if y > page.rect.height - 50 and re.fullmatch(r"Page \d+ of \d+", text):
                    continue
                rows.append((page_number, (y + bottom) / 2, x, text))
    rows.sort()
    markers = [(i, re.fullmatch(r"Message (\d+) of (\d+)", row[3]))
               for i, row in enumerate(rows) if row[2] < 60]
    markers = [(i, match) for i, match in markers if match]
    if not markers:
        raise OFWParseError("compact OFW report has no message markers")
    total = int(markers[0][1][2])
    if ([int(m[1]) for _, m in markers] != list(range(1, total + 1))
            or {int(m[2]) for _, m in markers} != {total}):
        raise OFWParseError("OFW message markers are incomplete or out of order")
    sha256 = sha256_bytes(data)
    messages = []
    for index, (start, _) in enumerate(markers):
        stop = markers[index + 1][0] if index + 1 < total else len(rows)
        block = rows[start + 1:stop]
        fields, body = _compact_header(block)
        normalized = "\n".join([
            "Sent: " + fields["SENT"], "From: " + fields["FROM"],
            "To: " + fields["TO"], "Subject: " + fields["SUBJECT"], "",
            *[row[3] for row in body],
        ])
        message = _parse_message_block(
            normalized, index + 1, total, timezone, report_timezone, names,
            case_id, document_id, sha256, rows[start][0], block[-1][0],
        )
        message.source_timezone_basis = "supplied"
        messages.append(message)
    if len({m.message_id for m in messages}) != total:
        raise OFWParseError("OFW report contains duplicate canonical message IDs")
    if any(a.sent_at > b.sent_at for a, b in zip(messages, messages[1:])):
        raise OFWParseError("OFW report messages are not in chronological order")
    return OFWParseResult(
        metadata=OFWReportMetadata(
            document_id=document_id, sha256=sha256, page_count=len(report),
            expected_message_count=total, parsed_message_count=total,
            timezone=report_timezone, timezone_basis="supplied", date_range_basis="messages",
            date_range_start=min(m.sent_at.date() for m in messages),
            date_range_end=max(m.sent_at.date() for m in messages),
            order="Chronological (oldest first, most recent last)",
        ),
        messages=messages,
    )


def _compact_header(rows):
    labels = {}
    for row in rows:
        if row[3] in {"SENT", "TO", "SUBJECT"} and row[2] < 60:
            labels.setdefault(row[3], row)
        elif row[3] == "FROM" and row[2] > 250:
            labels.setdefault("FROM", row)
        if len(labels) == 4:
            break
    if set(labels) != {"SENT", "FROM", "TO", "SUBJECT"}:
        raise OFWParseError("compact OFW message has an incomplete header")
    fields = {}
    for label, right in [("SENT", labels["FROM"][2]), ("FROM", float("inf"))]:
        anchor = labels[label]
        values = [r for r in rows if r[0] == anchor[0] and abs(r[1] - anchor[1]) < 6
                  and anchor[2] + 35 < r[2] < right]
        if not values:
            raise OFWParseError("compact OFW header has no value")
        fields[label] = " ".join(r[3] for r in values)
    to, subject = labels["TO"], labels["SUBJECT"]
    fields["TO"] = "\n".join(r[3] for r in rows if r[2] > to[2] + 35
                             and (to[0], to[1] - 6) <= r[:2] < (subject[0], subject[1] - 6))
    after_subject = [r for r in rows if r[:2] >= (subject[0], subject[1] - 6) and r != subject]
    body_index = next((i for i, r in enumerate(after_subject) if r[2] < subject[2] + 35), len(after_subject))
    fields["SUBJECT"] = " ".join(r[3] for r in after_subject[:body_index])
    return fields, after_subject[body_index:]
