#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.utils.case_intake import DEFAULT_OUTPUT_ROOT, SUPPORTED_EXTENSIONS, run_case_intake


def _parse_exts(value: str) -> set[str]:
    if not value:
        return set(SUPPORTED_EXTENSIONS)

    exts = set()
    for raw in value.split(","):
        item = raw.strip().lower()
        if not item:
            continue
        if not item.startswith("."):
            item = f".{item}"
        exts.add(item)
    return exts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a source-preserving case intake package: copied files, hashes, "
            "extracted text, manifest, timeline draft, proof-gap report, dashboard JSON, and ZIP."
        )
    )
    parser.add_argument(
        "--case-id",
        default="BCSC_138865_Watson_v_McClean",
        help="Case identifier for output files",
    )
    parser.add_argument(
        "--source-folder",
        default=None,
        help="Folder containing source legal/evidence files. Originals are copied, not moved.",
    )
    parser.add_argument(
        "--source-file",
        action="append",
        default=[],
        help="Exact source file to include. Can be repeated and can be used without --source-folder.",
    )
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_ROOT),
        help=f"Folder where the dated intake output is written (default: {DEFAULT_OUTPUT_ROOT})",
    )
    parser.add_argument(
        "--include-ext",
        default=",".join(sorted(SUPPORTED_EXTENSIONS)),
        help="Comma-separated extensions to include",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Only scan files directly inside --source-folder",
    )
    parser.add_argument(
        "--run-label",
        default=None,
        help="Optional exact output folder name under --output-root",
    )
    parser.add_argument(
        "--ocr-scanned-pdfs",
        action="store_true",
        help="Run OCR fallback on scanned PDFs. Slower; first intake pass leaves this off.",
    )
    parser.add_argument(
        "--ocr-text-dir",
        default=None,
        help="Folder containing sidecar OCR files named <source-stem>_OCR.txt.",
    )
    parser.add_argument(
        "--prefer-ocr-sidecar",
        action="store_true",
        help="Use matching sidecar OCR text even when the source file already has embedded text.",
    )
    parser.add_argument(
        "--max-pdf-pages",
        type=int,
        default=25,
        help="Maximum PDF pages to inspect per file (default: 25)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if not args.source_folder and not args.source_file:
            raise ValueError("Provide --source-folder or at least one --source-file")

        result = run_case_intake(
            case_id=args.case_id,
            source_folder=Path(args.source_folder) if args.source_folder else None,
            output_root=Path(args.output_root),
            recursive=not args.no_recursive,
            include_ext=_parse_exts(args.include_ext),
            source_files=[Path(path) for path in args.source_file],
            run_label=args.run_label,
            ocr_scanned_pdfs=args.ocr_scanned_pdfs,
            ocr_text_dir=Path(args.ocr_text_dir) if args.ocr_text_dir else None,
            prefer_ocr_sidecar=args.prefer_ocr_sidecar,
            max_pdf_pages=args.max_pdf_pages,
        )
    except Exception as exc:
        print(f"Case intake failed: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "status": "ok",
                "files": result.file_count,
                "output_dir": str(result.output_dir),
                "manifest_csv": str(result.manifest_path),
                "timeline_csv": str(result.timeline_csv_path),
                "proof_gaps_md": str(result.proof_gaps_path),
                "dashboard_json": str(result.dashboard_path),
                "archive_zip": str(result.archive_path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
