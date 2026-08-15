from pathlib import Path
import zipfile
import os
import shutil

# Default root for exported ZIPs (tests will monkeypatch this)
EXPORT_ROOT = Path(__file__).resolve().parents[3] / "exports"
# Tests also expect TMP_DIR to exist as an attribute they can patch.
TMP_DIR = EXPORT_ROOT / "tmp"


def zip_folder(folder: Path) -> Path:
    """
    Create a ZIP file from a folder.

    Tests expect:
      - ZIP created inside EXPORT_ROOT
      - EXPORT_ROOT / TMP_DIR can be monkeypatched
      - filename ends with '_export.zip'
      - function returns the full path to the ZIP
    """
    folder = Path(folder).expanduser()
    if not folder.exists():
        raise FileNotFoundError(f"Folder does not exist: {folder}")

    # Make sure patched EXPORT_ROOT exists
    EXPORT_ROOT.mkdir(parents=True, exist_ok=True)

    zip_name = f"{folder.name}_export.zip"
    zip_path = EXPORT_ROOT / zip_name

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(folder):
            for file in files:
                full_path = Path(root) / file
                rel_path = full_path.relative_to(folder)
                zipf.write(full_path, rel_path)

    return zip_path

def generate_evidence_zip(folder: Path) -> Path:
    """
    Backward-compatibility wrapper expected by router and tests.
    Delegates to the canonical zip_folder implementation.
    """
    return zip_folder(folder)


def generate_court_bundle_zip(source_folder: Path) -> Path:
    """Create a source-adjacent ZIP for a court bundle."""
    folder_path = Path(source_folder).expanduser()
    if not folder_path.exists():
        raise FileNotFoundError(f"Source folder does not exist: {folder_path}")
    if not folder_path.is_dir():
        raise NotADirectoryError(f"Source path is not a directory: {folder_path}")

    # Path.with_suffix() would turn ``case.v1`` into ``case.zip``. make_archive
    # appends ``.zip``, so construct the cleanup path the same way.
    zip_path = Path(f"{folder_path}.zip")
    if zip_path.exists():
        zip_path.unlink()

    shutil.make_archive(str(folder_path), "zip", root_dir=folder_path)
    return zip_path
