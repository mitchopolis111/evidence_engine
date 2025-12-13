from pathlib import Path
import shutil


def should_process_file(path: Path) -> bool:
    return (
        path.is_file()
        and not path.name.startswith(".")
        and path.suffix.lower() not in ["", ".ds_store"]
    )


def process_file(path: Path, case_id: str, router_callback):
    """
    router_callback is just a placeholder for test mocks.
    Watcher never generates narrative, OCR, or timeline.
    """
    dest_root = Path("~/Mitchopolis/cases").expanduser()
    dest_dir = dest_root / case_id / "source_evidence"
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest = dest_dir / path.name
    shutil.move(str(path), str(dest))

    return dest