#!/usr/bin/env python3
import argparse
import json
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Iterable, List, Optional, Set

import httpx

DEFAULT_ENDPOINT = "http://127.0.0.1:8000/api/evidence/process"


def _normalize_ext_list(value: str) -> Set[str]:
    if not value:
        return set()
    exts: Set[str] = set()
    for raw in value.split(","):
        item = raw.strip().lower()
        if not item:
            continue
        if not item.startswith("."):
            item = f".{item}"
        exts.add(item)
    return exts


def _iter_candidate_files(inbox: Path, include_ext: Set[str]) -> Iterable[Path]:
    if not inbox.exists():
        return []
    for path in inbox.iterdir():
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue
        if path.parent.name in {"_failed", "_processing"}:
            continue
        if include_ext and path.suffix.lower() not in include_ext:
            continue
        yield path


def _is_stable(path: Path, settle_seconds: float) -> bool:
    try:
        size1 = path.stat().st_size
    except FileNotFoundError:
        return False
    time.sleep(settle_seconds)
    try:
        size2 = path.stat().st_size
    except FileNotFoundError:
        return False
    return size1 == size2


def _safe_move(src: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if not dest.exists():
        shutil.move(str(src), str(dest))
        return dest
    stem = dest.stem
    suffix = dest.suffix
    counter = 1
    while True:
        candidate = dest_dir / f"{stem}__dup{counter}{suffix}"
        if not candidate.exists():
            shutil.move(str(src), str(candidate))
            return candidate
        counter += 1


def _build_payload(
    case_id: str,
    file_path: Path,
    source: str,
    tags: List[str],
) -> dict:
    use_tags = [t for t in tags if t]
    if "watcher" not in use_tags:
        use_tags.append("watcher")
    return {
        "case_id": case_id,
        "items": [
            {
                "id": str(uuid.uuid4()),
                "source": source,
                "content": f"Evidence file: {file_path.name}",
                "media_path": str(file_path),
                "tags": use_tags,
            }
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Watch an inbox folder and ingest new evidence files.",
    )
    parser.add_argument("--case-id", required=True, help="Case identifier")
    parser.add_argument(
        "--inbox",
        default="~/Mitchopolis/parenting_evidence/inbox",
        help="Inbox folder to watch",
    )
    parser.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        help=f"Evidence API endpoint (default: {DEFAULT_ENDPOINT})",
    )
    parser.add_argument(
        "--include-ext",
        default="",
        help="Comma-separated list of extensions to include (e.g. .pdf,.docx)",
    )
    parser.add_argument(
        "--source",
        default="inbox",
        help="Evidence source label (default: inbox)",
    )
    parser.add_argument(
        "--tag",
        action="append",
        default=[],
        help="Additional tag (can be repeated)",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=5.0,
        help="Polling interval in seconds (default: 5)",
    )
    parser.add_argument(
        "--settle-seconds",
        type=float,
        default=2.0,
        help="Seconds to wait for file size to stabilize (default: 2)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Scan once and exit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be ingested without calling the API",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inbox = Path(args.inbox).expanduser().resolve()
    include_ext = _normalize_ext_list(args.include_ext)
    failed_dir = inbox / "_failed"
    processing_dir = inbox / "_processing"

    if not inbox.exists():
        print(f"Inbox not found: {inbox}", file=sys.stderr)
        return 1

    timeout = httpx.Timeout(60.0, connect=10.0)
    client = httpx.Client(timeout=timeout)

    try:
        while True:
            candidates = list(_iter_candidate_files(inbox, include_ext))
            if candidates:
                print(f"Found {len(candidates)} file(s) to ingest.")
            for file_path in candidates:
                if not _is_stable(file_path, args.settle_seconds):
                    continue

                if args.dry_run:
                    payload = _build_payload(args.case_id, file_path, args.source, args.tag)
                    print(json.dumps(payload, indent=2))
                    continue

                staged = _safe_move(file_path, processing_dir)
                payload = _build_payload(args.case_id, staged, args.source, args.tag)

                try:
                    response = client.post(args.endpoint, json=payload)
                except httpx.RequestError as exc:
                    print(f"Request failed for {staged}: {exc}", file=sys.stderr)
                    _safe_move(staged, failed_dir)
                    continue

                if response.status_code >= 400:
                    print(
                        f"API error {response.status_code} for {staged}: {response.text}",
                        file=sys.stderr,
                    )
                    _safe_move(staged, failed_dir)
                    continue

                case_dir = Path("~/Mitchopolis/cases").expanduser() / args.case_id / "source_evidence"
                final_path = _safe_move(staged, case_dir)
                print(f"Ingested and moved to: {final_path}")

            if args.once:
                break
            time.sleep(args.poll_seconds)
    finally:
        client.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
