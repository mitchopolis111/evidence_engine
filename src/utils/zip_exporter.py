from pathlib import Path
import shutil


def generate_evidence_zip(source_folder: Path) -> Path:
    """Create a ZIP archive containing all files inside the given folder."""
    folder_path = Path(source_folder)
    if not folder_path.exists():
        raise FileNotFoundError(f"Source folder does not exist: {folder_path}")
    if not folder_path.is_dir():
        raise NotADirectoryError(f"Source path is not a directory: {folder_path}")

    zip_path = folder_path.with_suffix(".zip")
    if zip_path.exists():
        zip_path.unlink()

    shutil.make_archive(str(folder_path), "zip", root_dir=folder_path)
    return zip_path
