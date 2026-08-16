from pathlib import Path
import zipfile
import os
import shutil
import stat
import tempfile

# Default root for exported ZIPs (tests will monkeypatch this)
EXPORT_ROOT = Path(__file__).resolve().parents[3] / "exports"
# Tests also expect TMP_DIR to exist as an attribute they can patch.
TMP_DIR = EXPORT_ROOT / "tmp"

ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


class UnsafeExportPathError(ValueError):
    """Raised when an export source contains entries that are unsafe to follow."""


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _iter_export_files(folder: Path):
    """Yield regular source files in stable order without following symlinks."""
    for root, dirs, files in os.walk(folder, topdown=True, followlinks=False):
        root_path = Path(root)
        dirs.sort()
        files.sort()

        for dirname in dirs:
            directory = root_path / dirname
            if directory.is_symlink():
                relative = directory.relative_to(folder)
                raise UnsafeExportPathError(
                    f"Export source contains a symbolic link: {relative}"
                )

        for filename in files:
            source_path = root_path / filename
            relative = source_path.relative_to(folder)
            if source_path.is_symlink():
                raise UnsafeExportPathError(
                    f"Export source contains a symbolic link: {relative}"
                )

            resolved_path = source_path.resolve(strict=True)
            if not _is_within(resolved_path, folder):
                raise UnsafeExportPathError(
                    f"Export source escapes its approved folder: {relative}"
                )
            if not stat.S_ISREG(resolved_path.stat().st_mode):
                raise UnsafeExportPathError(
                    f"Export source contains a non-regular file: {relative}"
                )

            yield resolved_path, relative.as_posix()


def zip_folder(folder: Path) -> Path:
    """
    Create a ZIP file from a folder.

    Tests expect:
      - ZIP created inside EXPORT_ROOT
      - EXPORT_ROOT / TMP_DIR can be monkeypatched
      - filename ends with '_export.zip'
      - function returns the full path to the ZIP
    """
    folder = Path(folder).expanduser().resolve(strict=True)
    if not folder.is_dir():
        raise NotADirectoryError(f"Source path is not a directory: {folder}")

    # Make sure patched EXPORT_ROOT exists
    export_root = Path(EXPORT_ROOT).expanduser().resolve(strict=False)
    export_root.mkdir(parents=True, exist_ok=True)
    export_root = export_root.resolve(strict=True)
    if _is_within(export_root, folder):
        raise UnsafeExportPathError(
            "Export destination must be outside the source folder"
        )

    zip_name = f"{folder.name}_export.zip"
    zip_path = export_root / zip_name

    temporary = tempfile.NamedTemporaryFile(
        dir=export_root,
        prefix=f".{zip_name}.",
        suffix=".tmp",
        delete=False,
    )
    temporary_path = Path(temporary.name)
    temporary.close()

    try:
        with zipfile.ZipFile(temporary_path, "w") as zipf:
            for source_path, archive_name in _iter_export_files(folder):
                archive_info = zipfile.ZipInfo(archive_name, ZIP_TIMESTAMP)
                archive_info.compress_type = zipfile.ZIP_DEFLATED
                archive_info.create_system = 3
                archive_info.external_attr = (stat.S_IFREG | 0o644) << 16

                with source_path.open("rb") as source, zipf.open(
                    archive_info, "w", force_zip64=True
                ) as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)

        temporary_path.replace(zip_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

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
