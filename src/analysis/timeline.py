from __future__ import annotations
import re
from typing import Optional, List, Dict, Any

# --------------------------------------------------------------------
# DATE EXTRACTION UTILITIES
# Tests expect:
#   - ISO dates ("2025-11-20")
#   - Month-name formats ("November 20, 2025")
#   - Compact filename dates ("OFW_Messages_2025-12-01.pdf")
# --------------------------------------------------------------------

ISO_PATTERN = re.compile(r"(20\d{2})-(\d{2})-(\d{2})")
MONTH_PATTERN = re.compile(
    r"\b("
    r"January|February|March|April|May|June|July|August|September|October|November|December"
    r")\s+(\d{1,2}),\s*(20\d{2})\b",
    re.IGNORECASE,
)


def extract_timestamp(text: str) -> Optional[str]:
    """Primary extractor: handles ISO and month-name formats."""
    if not text:
        return None

    # ISO: 2025-11-20 (in text OR filenames)
    m = ISO_PATTERN.search(text)
    if m:
        return m.group(0)

    # Month-name: November 20, 2025
    m = MONTH_PATTERN.search(text)
    if m:
        month_name, day, year = m.groups()

        month_map = {
            "january": "01",
            "february": "02",
            "march": "03",
            "april": "04",
            "may": "05",
            "june": "06",
            "july": "07",
            "august": "08",
            "september": "09",
            "october": "10",
            "november": "11",
            "december": "12",
        }

        month_num = month_map[month_name.lower()]
        return f"{year}-{month_num:>02}-{int(day):02d}".replace(" ", "0")

    return None


def extract_date(text: str) -> Optional[str]:
    """
    Wrapper used by tests:
    - Try extract_timestamp first
    - Then fallback to any YYYY-MM-DD inside the string (filenames)
    """
    if not text:
        return None

    # 1) Try main extractor
    ts = extract_timestamp(text)
    if ts:
        return ts

    # 2) Fallback: compact filename patterns like OFW_Messages_2025-12-01.pdf
    m = re.search(r"(20\d{2}-\d{2}-\d{2})", text)
    if m:
        return m.group(1)

    return None


# --------------------------------------------------------------------
# TIMELINE ENTRY STORAGE MODEL (non-Pydantic)
# --------------------------------------------------------------------

class TimelineEntry:
    def __init__(
        self,
        id: Optional[str],
        case_id: str,
        summary: str,
        timestamp: Optional[str],
        evidence_ids: List[str],
        predicted_type: str,
        ocr_used: bool,
        media_path: Optional[str],
        narrative: Dict[str, Any],
    ):
        self.id = id
        self.case_id = case_id
        self.summary = summary
        self.timestamp = timestamp
        self.evidence_ids = evidence_ids
        self.predicted_type = predicted_type
        self.ocr_used = ocr_used
        self.media_path = media_path
        self.narrative = narrative


# --------------------------------------------------------------------
# GLOBAL STORE + APPENDER
# --------------------------------------------------------------------

TIMELINE_STORE: List[TimelineEntry] = []


def append_timeline_entry(entry: TimelineEntry):
    TIMELINE_STORE.append(entry)