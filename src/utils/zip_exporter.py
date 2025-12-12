from pathlib import Path
import zipfile
import os

# Default root for exported ZIPs (tests will monkeypatch this)
EXPORT_ROOT = Path("~/Mitchopolis/exports").expanduser()
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