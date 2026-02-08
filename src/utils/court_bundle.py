from pathlib import Path
from .zip_exporter import generate_evidence_zip


def build_court_bundle(case_id: str, source_folder: Path) -> Path:
    """
    v1: Generate a ZIP bundle for the given case.
    Later: Add PDF timeline and index.
    """
    return generate_evidence_zip(source_folder)
