from __future__ import annotations

import bisect
import hashlib
import re
from datetime import date, datetime, timezone as datetime_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import fitz
from pydantic import BaseModel, Field, field_validator

from .case_intelligence import (
    CASE_ID,
    PERSON_ID_BY_DISPLAY_NAME,
    SHA256_PATTERN,
    OFWAttachment,
    OFWMessage,
    OFWReadReceipt,
    SourceRef,
    sha256_bytes,
)

MESSAGE_MARKER_RE = re.compile(
    r"(?m)^[ \t]*Message\s+(\d+)\s+of\s+(\d+)[ \t]*$"
)
FIELD_RE = re.compile(r"^\s*(Sent|From|To|Subject):\s*(.*)$", re.IGNORECASE)
DATETIME_RE = re.compile(r"(\d{2}/\d{2}/\d{4})\s*(\d{1,2}:\d{2})\s*([AP]M)", re.IGNORECASE)
READ_RECEIPT_RE = re.compile(
    r"^(?P<name>.*?)\s*(?:\(First\s*Viewed\s*:\s*(?P<viewed>.*?)\))?$",
    re.IGNORECASE,
)
ATTACHMENT_RE = re.compile(
    r"(?:^|,\s*)(?P<filename>.+?)\s*"
    r"\((?P<size>[0-9.]+\s*(?:B|KB|MB|GB))\)(?=,\s*|[ \t\f]*$)",
    re.IGNORECASE,
)
FOOTER_RE = re.compile(r"(?m)^\s*\|?\s*Message Report\s+Page\s+\d+\s+of\s+\d+\s*$")


class OFWParseError(ValueError):
    pass


class OFWReportMetadata(BaseModel):
    document_id: str
    sha256: str = Field(pattern=SHA256_PATTERN)
    page_count: int
    expected_message_count: int
    parsed_message_count: int
    timezone: str
    date_range_start: date
    date_range_end: date
    order: str
    generated_at_raw: str | None = None

    @field_validator("sha256")
    @classmethod
    def normalize_sha256(cls, value: str) -> str:
        return value.lower()


class OFWParseResult(BaseModel):
    metadata: OFWReportMetadata
    messages: list[OFWMessage]


def parse_ofw_message_report(
    data: bytes,
    document_id: str,
    case_id: str = CASE_ID,
    person_id_by_display_name: dict[str, str] | None = None,
) -> OFWParseResult:
    if not data:
        raise OFWParseError("OFW report is empty")

    try:
        with fitz.open(stream=data, filetype="pdf") as report:
            if report.page_count < 1:
                raise OFWParseError("OFW report has no pages")
            pages = [page.get_text("text", sort=True) for page in report]
    except OFWParseError:
        raise
    except Exception as exc:
        raise OFWParseError("unable to read OFW PDF") from exc

    return parse_ofw_message_report_pages(
        pages=pages,
        document_id=document_id,
        source_sha256=sha256_bytes(data),
        case_id=case_id,
        person_id_by_display_name=person_id_by_display_name,
    )


def parse_ofw_message_report_pages(
    pages: list[str],
    document_id: str,
    source_sha256: str,
    case_id: str = CASE_ID,
    person_id_by_display_name: dict[str, str] | None = None,
) -> OFWParseResult:
    if not pages:
        raise OFWParseError("OFW report has no pages")

    display_names = {
        _normalize_name(name): person_id for name, person_id in PERSON_ID_BY_DISPLAY_NAME.items()
    }
    if person_id_by_display_name:
        display_names.update(
            {_normalize_name(name): person_id for name, person_id in person_id_by_display_name.items()}
        )

    timezone_name = _extract_required_metadata(pages[0], "Timezone", r"[A-Za-z_+-]+/[A-Za-z_+-]+")
    expected_count_text = _extract_required_metadata(pages[0], "Contains", r"\d+")
    expected_count = int(expected_count_text)
    date_range_start, date_range_end = _extract_date_range(pages[0])
    order = _extract_required_metadata(
        pages[0],
        "Order",
        r"Chronological\s*\(oldest first,\s*most recent last\)",
    )
    generated_at_match = re.search(r"Generated:\s*([^\n]+?)(?:\s{2,}|\n)", pages[0])
    generated_at_raw = generated_at_match.group(1).strip() if generated_at_match else None

    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise OFWParseError(f"unknown OFW report timezone: {timezone_name}") from exc

    cleaned_pages = [_clean_page(page) for page in pages]
    page_offsets: list[int] = []
    chunks: list[str] = []
    offset = 0
    for page in cleaned_pages:
        page_offsets.append(offset)
        chunk = page + "\n\f\n"
        chunks.append(chunk)
        offset += len(chunk)
    report_text = "".join(chunks)
    markers = list(MESSAGE_MARKER_RE.finditer(report_text))

    if len(markers) != expected_count:
        raise OFWParseError(
            f"OFW marker count mismatch: header={expected_count}, parsed={len(markers)}"
        )

    marker_numbers = [int(marker.group(1)) for marker in markers]
    marker_totals = {int(marker.group(2)) for marker in markers}
    if marker_numbers != list(range(1, expected_count + 1)) or marker_totals != {expected_count}:
        raise OFWParseError("OFW message markers are incomplete or out of order")

    messages: list[OFWMessage] = []
    for index, marker in enumerate(markers):
        number = int(marker.group(1))
        block_end = markers[index + 1].start() if index + 1 < len(markers) else len(report_text)
        block = report_text[marker.end():block_end]
        top_level_end = _top_level_block_end(block, number)
        start_page = bisect.bisect_right(page_offsets, marker.start())
        end_page = bisect.bisect_right(
            page_offsets,
            max(marker.start(), marker.end() + top_level_end - 1),
        )
        messages.append(
            _parse_message_block(
                block=block,
                number=number,
                total=expected_count,
                timezone=timezone,
                timezone_name=timezone_name,
                display_names=display_names,
                case_id=case_id,
                document_id=document_id,
                source_sha256=source_sha256,
                start_page=start_page,
                end_page=end_page,
            )
        )

    message_ids = [message.message_id for message in messages]
    if len(message_ids) != len(set(message_ids)):
        raise OFWParseError("OFW report contains duplicate canonical message IDs")
    if any(
        earlier.sent_at > later.sent_at
        for earlier, later in zip(messages, messages[1:])
    ):
        raise OFWParseError("OFW report messages are not in chronological order")
    if any(
        not date_range_start <= message.sent_at.date() <= date_range_end
        for message in messages
    ):
        raise OFWParseError("OFW message falls outside the declared date range")

    return OFWParseResult(
        metadata=OFWReportMetadata(
            document_id=document_id,
            sha256=source_sha256,
            page_count=len(pages),
            expected_message_count=expected_count,
            parsed_message_count=len(messages),
            timezone=timezone_name,
            date_range_start=date_range_start,
            date_range_end=date_range_end,
            order=order,
            generated_at_raw=generated_at_raw,
        ),
        messages=messages,
    )


def _parse_message_block(
    block: str,
    number: int,
    total: int,
    timezone: ZoneInfo,
    timezone_name: str,
    display_names: dict[str, str],
    case_id: str,
    document_id: str,
    source_sha256: str,
    start_page: int,
    end_page: int,
) -> OFWMessage:
    lines = block.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    fields, body_start = _parse_first_header(lines, number)
    nested_header_start = _find_nested_header(lines, body_start)
    body, attachments = _parse_body(lines[body_start:nested_header_start])

    sent_at_raw = _normalize_datetime_text(fields["sent"])
    sent_at = _parse_local_datetime(sent_at_raw, timezone)
    sender_person_id = _resolve_person(fields["from"], display_names, number)
    recipients, read_receipts = _parse_recipients(
        fields["to"], display_names, number, timezone
    )
    read_times = [
        receipt.first_viewed_at for receipt in read_receipts if receipt.first_viewed_at is not None
    ]
    read_at = min(read_times) if len(recipients) == 1 and read_times else None
    subject = _normalize_inline_text(fields["subject"])
    content_sha256 = _message_fingerprint(
        sent_at=sent_at,
        sender_person_id=sender_person_id,
        recipient_person_ids=recipients,
        subject=subject,
        body=body,
        attachments=attachments,
    )

    return OFWMessage(
        message_id=f"ofw_{content_sha256[:32]}",
        case_id=case_id,
        sender_person_id=sender_person_id,
        recipient_person_ids=recipients,
        sent_at=sent_at,
        sent_at_raw=sent_at_raw,
        source_timezone=timezone_name,
        read_at=read_at,
        read_receipts=read_receipts,
        subject=subject,
        body=body,
        attachments=attachments,
        report_message_number=number,
        report_message_total=total,
        content_sha256=content_sha256,
        source=SourceRef(
            document_id=document_id,
            sha256=source_sha256,
            page=start_page,
            end_page=max(start_page, end_page),
            record_locator=f"message:{number}/{total}",
            source_type="ofw_message_report",
            extraction_method="native",
            confidence=1.0,
        ),
    )


def _parse_first_header(lines: list[str], number: int) -> tuple[dict[str, str], int]:
    expected = ["sent", "from", "to", "subject"]
    start = next(
        (
            index
            for index, line in enumerate(lines[:30])
            if (match := FIELD_RE.match(line)) and match.group(1).lower() == "sent"
        ),
        None,
    )
    if start is None:
        raise OFWParseError(f"message {number} is missing its Sent header")

    fields: dict[str, str] = {}
    cursor = start
    for expected_index, expected_name in enumerate(expected):
        while cursor < len(lines) and not lines[cursor].strip():
            cursor += 1
        if cursor >= len(lines):
            raise OFWParseError(f"message {number} has an incomplete header")
        match = FIELD_RE.match(lines[cursor])
        if match is None or match.group(1).lower() != expected_name:
            raise OFWParseError(f"message {number} is missing its {expected_name.title()} header")

        values = [match.group(2).strip()] if match.group(2).strip() else []
        cursor += 1
        if expected_name == "subject":
            while cursor < len(lines) and lines[cursor].strip():
                if FIELD_RE.match(lines[cursor]):
                    break
                values.append(lines[cursor].strip())
                cursor += 1
            while cursor < len(lines) and not lines[cursor].strip():
                cursor += 1
        else:
            next_name = expected[expected_index + 1]
            while cursor < len(lines):
                next_match = FIELD_RE.match(lines[cursor])
                if next_match is not None and next_match.group(1).lower() == next_name:
                    break
                if lines[cursor].strip():
                    values.append(lines[cursor].strip())
                cursor += 1
        separator = "\n" if expected_name == "to" else " "
        fields[expected_name] = separator.join(values).strip()

    return fields, cursor


def _find_nested_header(lines: list[str], body_start: int) -> int:
    for index in range(body_start, len(lines)):
        match = FIELD_RE.match(lines[index])
        if match is None or match.group(1).lower() != "sent":
            continue
        if DATETIME_RE.search(match.group(2)) is None:
            continue
        labels: list[str] = []
        for candidate in lines[index:index + 16]:
            candidate_match = FIELD_RE.match(candidate)
            if candidate_match:
                labels.append(candidate_match.group(1).lower())
            if labels == ["sent", "from", "to", "subject"]:
                return index
    return len(lines)


def _parse_body(lines: list[str]) -> tuple[str, list[OFWAttachment]]:
    cleaned_lines = [line.strip() for line in lines]
    attachment_index = next(
        (index for index, line in enumerate(cleaned_lines) if line.startswith("See Attachments:")),
        None,
    )
    attachment_text = ""
    if attachment_index is not None:
        attachment_text = " ".join(cleaned_lines[attachment_index:])
        cleaned_lines = cleaned_lines[:attachment_index]

    paragraphs: list[str] = []
    current: list[str] = []
    for line in cleaned_lines:
        if not line:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        current.append(line)
    if current:
        paragraphs.append(" ".join(current))
    body = "\n\n".join(paragraphs).strip()

    matches = list(ATTACHMENT_RE.finditer(attachment_text))
    if attachment_text and (
        not matches
        or matches[0].start() != 0
        or any(left.end() != right.start() for left, right in zip(matches, matches[1:]))
        or attachment_text[matches[-1].end():].strip(" \t\r\n\f")
    ):
        raise OFWParseError("unable to fully parse OFW attachment list")

    attachments: list[OFWAttachment] = []
    for match in matches:
        raw_filename = match.group("filename").removeprefix("See Attachments:").strip()
        attachments.append(
            OFWAttachment(
                filename=_normalize_attachment_filename(raw_filename),
                raw_filename=raw_filename,
                display_size=_normalize_inline_text(match.group("size")),
            )
        )
    return body, attachments


def _parse_recipients(
    raw_value: str,
    display_names: dict[str, str],
    number: int,
    timezone: ZoneInfo,
) -> tuple[list[str], list[OFWReadReceipt]]:
    normalized = raw_value.replace("FirstViewed", "First Viewed")
    parts: list[str] = []
    for recipient_line in normalized.splitlines():
        parts.extend(re.split(r",\s*(?=[A-Za-z][^()]*(?:\(|$))", recipient_line))
    recipients: list[str] = []
    receipts: list[OFWReadReceipt] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        match = READ_RECEIPT_RE.match(part)
        if match is None:
            raise OFWParseError(f"message {number} has an invalid To header")
        person_id = _resolve_person(match.group("name"), display_names, number)
        viewed_raw = match.group("viewed")
        viewed_at = None
        normalized_viewed_raw = None
        if viewed_raw:
            viewed_raw = viewed_raw.strip()
            if viewed_raw.casefold() in {"never", "not viewed"}:
                normalized_viewed_raw = viewed_raw
            else:
                normalized_viewed_raw = _normalize_datetime_text(viewed_raw)
                viewed_at = _parse_local_datetime(normalized_viewed_raw, timezone)
        recipients.append(person_id)
        receipts.append(
            OFWReadReceipt(
                recipient_person_id=person_id,
                first_viewed_at=viewed_at,
                first_viewed_at_raw=normalized_viewed_raw,
            )
        )
    if not recipients:
        raise OFWParseError(f"message {number} has no recipients")
    return recipients, receipts


def _message_fingerprint(
    sent_at: datetime,
    sender_person_id: str,
    recipient_person_ids: list[str],
    subject: str,
    body: str,
    attachments: list[OFWAttachment],
) -> str:
    canonical = "\x1f".join(
        [
            sent_at.astimezone(datetime_timezone.utc).isoformat(),
            sender_person_id,
            ",".join(sorted(recipient_person_ids)),
            _normalize_inline_text(subject),
            re.sub(r"\s+", " ", body).strip(),
            "\x1e".join(
                sorted(
                    f"{attachment.filename}\x1d{attachment.display_size or ''}"
                    for attachment in attachments
                )
            ),
        ]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _resolve_person(raw_name: str, display_names: dict[str, str], number: int) -> str:
    name = _normalize_name(raw_name)
    try:
        return display_names[name]
    except KeyError as exc:
        raise OFWParseError(f"message {number} references unknown person: {raw_name.strip()}") from exc


def _normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _normalize_inline_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _normalize_attachment_filename(value: str) -> str:
    return re.sub(r"\.\s+(?=[A-Za-z0-9]{2,8}$)", ".", value.strip())


def _normalize_datetime_text(value: str) -> str:
    match = DATETIME_RE.search(value)
    if match is None:
        raise OFWParseError(f"invalid OFW datetime: {value}")
    return f"{match.group(1)} {match.group(2)} {match.group(3).upper()}"


def _parse_local_datetime(value: str, timezone: ZoneInfo) -> datetime:
    return datetime.strptime(value, "%m/%d/%Y %I:%M %p").replace(tzinfo=timezone)


def _extract_required_metadata(text: str, label: str, value_pattern: str) -> str:
    match = re.search(rf"{re.escape(label)}:\s*({value_pattern})", text, re.IGNORECASE)
    if match is None:
        raise OFWParseError(f"OFW report is missing {label} metadata")
    return match.group(1)


def _extract_date_range(text: str) -> tuple[date, date]:
    match = re.search(
        r"Date Range:\s*(\d{2}/\d{2}/\d{4})\s*[—–-]\s*(\d{2}/\d{2}/\d{4})",
        text,
        re.IGNORECASE,
    )
    if match is None:
        raise OFWParseError("OFW report is missing Date Range metadata")
    start = datetime.strptime(match.group(1), "%m/%d/%Y").date()
    end = datetime.strptime(match.group(2), "%m/%d/%Y").date()
    if end < start:
        raise OFWParseError("OFW report has an invalid date range")
    return start, end


def _top_level_block_end(block: str, number: int) -> int:
    normalized = block.replace("\r\n", "\n").replace("\r", "\n")
    lines_with_endings = normalized.splitlines(keepends=True)
    lines = [line.rstrip("\n") for line in lines_with_endings]
    _, body_start = _parse_first_header(lines, number)
    nested_header_start = _find_nested_header(lines, body_start)
    if nested_header_start == len(lines):
        prefix = normalized
    else:
        prefix = "".join(lines_with_endings[:nested_header_start])
    return len(prefix.rstrip("\n\f \t"))


def _clean_page(text: str) -> str:
    return FOOTER_RE.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))
