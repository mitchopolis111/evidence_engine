from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re
from typing import Any, Dict, List, Optional, Union


_MONTH_NUMBERS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sept": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}
_MONTH_TOKEN = "|".join(
    sorted(_MONTH_NUMBERS, key=len, reverse=True)
)

ISO_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(20\d{2})[-/](\d{1,2})[-/](\d{1,2})"
    r"(?![A-Za-z0-9])"
)
MONTH_PATTERN = re.compile(
    rf"(?<![A-Za-z0-9])({_MONTH_TOKEN})\.?\s+(\d{{1,2}})"
    rf"(?:st|nd|rd|th)?(?:,\s*|\s+)(20\d{{2}})(?![A-Za-z0-9])",
    re.IGNORECASE,
)
DAY_MONTH_PATTERN = re.compile(
    rf"(?<![A-Za-z0-9])(\d{{1,2}})[-\s]({_MONTH_TOKEN})\.?"
    rf"[-\s](20\d{{2}})(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def _normalized_date(
    year: str, month: Union[int, str], day: str
) -> Optional[str]:
    try:
        return date(int(year), int(month), int(day)).isoformat()
    except (TypeError, ValueError):
        return None


def _month_number(month_name: str) -> int:
    return _MONTH_NUMBERS[month_name.lower().rstrip(".")]


def extract_date(text: str) -> Optional[str]:
    """Return the earliest valid supported date normalized to ISO format."""
    if not text:
        return None

    candidates: list[tuple[int, str]] = []

    for match in ISO_PATTERN.finditer(text):
        normalized = _normalized_date(*match.groups())
        if normalized:
            candidates.append((match.start(), normalized))

    for match in MONTH_PATTERN.finditer(text):
        month_name, day, year = match.groups()
        normalized = _normalized_date(year, _month_number(month_name), day)
        if normalized:
            candidates.append((match.start(), normalized))

    for match in DAY_MONTH_PATTERN.finditer(text):
        day, month_name, year = match.groups()
        normalized = _normalized_date(year, _month_number(month_name), day)
        if normalized:
            candidates.append((match.start(), normalized))

    if not candidates:
        return None
    return min(candidates, key=lambda candidate: candidate[0])[1]


def extract_timestamp(text: str) -> Optional[str]:
    """Compatibility name for the canonical date extractor."""
    return extract_date(text)


def build_timeline_item(text: str, classification: str) -> Dict[str, Any]:
    """Build a minimal timeline draft without inventing a missing date."""
    return {
        "date": extract_date(text),
        "summary": classification,
        "extract": text[:300],
    }


@dataclass
class TimelineEntry:
    """Legacy non-Pydantic timeline record retained for compatibility."""

    id: Optional[str]
    case_id: str
    summary: str
    timestamp: Optional[str]
    evidence_ids: List[str]
    predicted_type: str
    ocr_used: bool
    media_path: Optional[str]
    narrative: Dict[str, Any]


TIMELINE_STORE: List[TimelineEntry] = []


def append_timeline_entry(entry: TimelineEntry) -> None:
    TIMELINE_STORE.append(entry)


__all__ = [
    "DAY_MONTH_PATTERN",
    "ISO_PATTERN",
    "MONTH_PATTERN",
    "TIMELINE_STORE",
    "TimelineEntry",
    "append_timeline_entry",
    "build_timeline_item",
    "extract_date",
    "extract_timestamp",
]
