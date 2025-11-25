import os
import zipfile
from datetime import datetime
from pathlib import Path


EXPORT_ROOT = Path.home() / "Mitchopolis" / "parenting_evidence" / "exports"
TMP_DIR = EXPORT_ROOT / "tmp"


def ensure_directories():
    """
    Ensure required export folders exist.
    Safe, idempotent, no destructive operations.
    """
    EXPORT_ROOT.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)


def generate_export_filename(prefix: str = "evidence_export") -> str:
    """
    Create a timestamped ZIP filename.
    Example: evidence_export_2025-11-25T09-53-00.zip
    """
    ts = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    return f"{prefix}_{ts}.zip"


def create_zip_from_folder(source_folder: Path, output_zip_path: Path) -> Path:
    """
    Creates a ZIP archive from the given source folder.

    source_folder: Path to the folder containing evidence files.
    output_zip_path: Desired location for the resulting ZIP file.

    Returns the path to the ZIP.
    """
    if not source_folder.exists():
        raise FileNotFoundError(f"Source folder does not exist: {source_folder}")

    ensure_directories()

    with zipfile.ZipFile(output_zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_folder):
            for file in files:
                full_path = Path(root) / file
                relative_path = full_path.relative_to(source_folder)
                zipf.write(full_path, relative_path)

    return output_zip_path


def generate_evidence_zip(case_folder: Path) -> Path:
    """
    Convenience wrapper:
    - Builds a timestamped ZIP name
    - Zips the provided evidence folder
    - Stores result under parenting_evidence/exports
    """
    ensure_directories()

    zip_name = generate_export_filename()
    output_zip = EXPORT_ROOT / zip_name

    return create_zip_from_folder(case_folder, output_zip)
