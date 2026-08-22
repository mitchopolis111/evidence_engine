#!/usr/bin/env python3
import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Iterable, List, Optional, Set

import httpx

DEFAULT_ENDPOINT = "http://127.0.0.1:8000/api/evidence/process"


def _normalize_ext_list(value: str) -> Set[str]:
    if not value:
        return set()
    exts = set()
    for raw in value.split(","):
        item = raw.strip().lower()
        if not item:
            continue
        if not item.startswith("."):
            item = f".{item}"
        exts.add(item)
    return exts


def _iter_files(folder: Path, recursive: bool) -> Iterable[Path]:
    if recursive:
        yield from folder.rglob("*")
    else:
        yield from folder.iterdir()


def _collect_files(
    folder: Path,
    recursive: bool,
    include_ext: Set[str],
    exclude_ext: Set[str],
) -> List[Path]:
    files: List[Path] = []
    for path in _iter_files(folder, recursive):
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue
        ext = path.suffix.lower()
        if include_ext and ext not in include_ext:
            continue
        if exclude_ext and ext in exclude_ext:
            continue
        files.append(path)
    return sorted(files)


def _build_items(files: List[Path], source: str, tags: List[str]) -> List[dict]:
    items = []
    base_tags = [t for t in tags if t]
    if "batch" not in base_tags:
        base_tags.append("batch")

    for file_path in files:
        items.append(
            {
                "id": str(uuid.uuid4()),
                "source": source,
                "content": f"Evidence file: {file_path.name}",
                "media_path": str(file_path),
                "tags": base_tags,
            }
        )
    return items


def _chunk(items: List[dict], size: int) -> Iterable[List[dict]]:
    for idx in range(0, len(items), size):
        yield items[idx : idx + size]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch-ingest evidence files by calling the evidence API.",
    )
    parser.add_argument("--case-id", required=True, help="Case identifier")
    parser.add_argument("--folder", required=True, help="Folder of evidence files")
    parser.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        help=f"Evidence API endpoint (default: {DEFAULT_ENDPOINT})",
    )
    parser.add_argument(
        "--source",
        default="unsorted",
        help="Evidence source label (default: unsorted)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=25,
        help="Number of files per API request (default: 25)",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Include files from subfolders",
    )
    parser.add_argument(
        "--include-ext",
        default="",
        help="Comma-separated list of extensions to include (e.g. .pdf,.png)",
    )
    parser.add_argument(
        "--exclude-ext",
        default="",
        help="Comma-separated list of extensions to exclude",
    )
    parser.add_argument(
        "--file",
        action="append",
        default=[],
        help="Exact filename to include (can be repeated)",
    )
    parser.add_argument(
        "--tag",
        action="append",
        default=[],
        help="Additional tag (can be repeated)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the files and a sample payload without calling the API",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    folder = Path(args.folder).expanduser().resolve()
    if not folder.exists() or not folder.is_dir():
        print(f"Folder not found: {folder}", file=sys.stderr)
        return 1

    include_ext = _normalize_ext_list(args.include_ext)
    exclude_ext = _normalize_ext_list(args.exclude_ext)
    files = _collect_files(folder, args.recursive, include_ext, exclude_ext)

    file_filters = [f for f in args.file if f]
    if file_filters:
        allow = set(file_filters)
        files = [f for f in files if f.name in allow]

    if not files:
        if file_filters:
            print("No files matched --file filter.")
        else:
            print("No files found to ingest.")
        return 1

    items = _build_items(files, args.source, args.tag)

    if args.dry_run:
        print(f"Found {len(files)} files in {folder}")
        preview = items[: min(len(items), 3)]
        payload = {"case_id": args.case_id, "items": preview}
        print(json.dumps(payload, indent=2))
        return 0

    total_batches = (len(items) + args.batch_size - 1) // args.batch_size
    print(f"Preparing {len(items)} files in {total_batches} batch(es).")

    timeout = httpx.Timeout(60.0, connect=10.0)
    with httpx.Client(timeout=timeout) as client:
        for idx, batch in enumerate(_chunk(items, args.batch_size), start=1):
            payload = {"case_id": args.case_id, "items": batch}
            print(f"Sending batch {idx}/{total_batches} with {len(batch)} items...")
            try:
                response = client.post(args.endpoint, json=payload)
            except httpx.RequestError as exc:
                print(f"Request failed: {exc}", file=sys.stderr)
                return 1

            if response.status_code >= 400:
                print(
                    f"API error {response.status_code}: {response.text}",
                    file=sys.stderr,
                )
                return 1

            try:
                data = response.json()
            except ValueError:
                print("Non-JSON response from API.", file=sys.stderr)
                return 1

            classified_count = data.get("classified_count")
            print(f"Batch {idx} OK (classified_count={classified_count}).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
