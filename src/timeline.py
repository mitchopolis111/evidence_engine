import re
from datetime import datetime

def extract_date(text: str):
    match = re.search(r"(20\d{2}[-/]\d{1,2}[-/]\d{1,2})", text)
    if match:
        return match.group(1)
    return None

def build_timeline_item(text: str, classification: str):
    date = extract_date(text)
    return {
        "date": date or str(datetime.now().date()),
        "summary": classification,
        "extract": text[:300]
    }
