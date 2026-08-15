from pathlib import Path
import shutil


def generate_evidence_zip(source_folder: Path) -> Path:
    """Create a ZIP archive containing all files inside the given folder."""
    folder_path = Path(source_folder)
    if not folder_path.exists():
        raise FileNotFoundError(f"Source folder does not exist: {folder_path}")
    if not folder_path.is_dir():
        raise NotADirectoryError(f"Source path is not a directory: {folder_path}")

    # ``with_suffix`` would replace the final part of a dotted directory name
    # (for example, ``case.v1``), while ``make_archive`` appends ``.zip``.
    # Build the return path the same way so callers always receive the archive
    # that was actually created.
    zip_path = Path(f"{folder_path}.zip")
    if zip_path.exists():
        zip_path.unlink()

    shutil.make_archive(str(folder_path), "zip", root_dir=folder_path)
    return zip_path
