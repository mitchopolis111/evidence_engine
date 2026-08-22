import csv
import hashlib
import json
import re
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from src.classifier import classify_text
from src.ocr import safe_extract_text


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_ROOT = WORKSPACE_ROOT / "output"
SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".txt",
    ".log",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".bmp",
}

ISSUE_TERMS = {
    "court_file_138865": ["138865", "court file no", "watson", "mcclean"],
    "orders_agreements": [
        "consent order",
        "separation agreement",
        "parenting agreement",
        "supreme court",
        "filed",
    ],
    "ofw_messages": ["ourfamilywizard", "message report", "ofw"],
    "parenting_time_exchange": [
        "parenting time",
        "exchange",
        "raymer",
        "rcmp",
        "west kelowna",
        "attendance",
    ],
    "support_payments": ["bcfma", "family maintenance", "support payment", "payment"],
    "medical_coverage": ["medical", "coverage", "insurance", "benefits"],
    "school_childcare": ["school", "teacher", "raymer", "childcare", "pickup"],
}

MONTHS = {
    "january": "01",
    "jan": "01",
    "february": "02",
    "feb": "02",
    "march": "03",
    "mar": "03",
    "april": "04",
    "apr": "04",
    "may": "05",
    "june": "06",
    "jun": "06",
    "july": "07",
    "jul": "07",
    "august": "08",
    "aug": "08",
    "september": "09",
    "sept": "09",
    "sep": "09",
    "october": "10",
    "oct": "10",
    "november": "11",
    "nov": "11",
    "december": "12",
    "dec": "12",
}


@dataclass
class IntakeResult:
    output_dir: Path
    manifest_path: Path
    timeline_csv_path: Path
    timeline_json_path: Path
    proof_gaps_path: Path
    dashboard_path: Path
    archive_path: Path
    file_count: int


def _slugify(value: str, fallback: str = "case") -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_")
    return slug or fallback


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_folder_files(
    source_folder: Path,
    recursive: bool,
    include_ext: set[str],
) -> list[Path]:
    iterator: Iterable[Path]
    iterator = source_folder.rglob("*") if recursive else source_folder.iterdir()
    files = []
    for path in iterator:
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.suffix.lower() not in include_ext:
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.as_posix().lower())


def _collect_source_files(
    source_folder: Optional[Path],
    source_files: Optional[list[Path]],
    recursive: bool,
    include_ext: set[str],
) -> list[Path]:
    files: list[Path] = []
    if source_folder is not None:
        files.extend(_iter_folder_files(source_folder, recursive=recursive, include_ext=include_ext))

    for raw_path in source_files or []:
        path = Path(raw_path).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Source file not found: {path}")
        if path.suffix.lower() not in include_ext:
            continue
        files.append(path)

    deduped = {}
    for path in files:
        deduped[path.resolve()] = path

    return sorted(deduped.values(), key=lambda item: item.as_posix().lower())


def _safe_filename(index: int, path: Path) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._() -]+", "_", path.name).strip()
    return f"{index:03d}_{cleaned or 'document'}"


def _find_ocr_sidecar(source_path: Path, ocr_text_dir: Optional[Path]) -> Optional[Path]:
    if ocr_text_dir is None:
        return None

    candidate = ocr_text_dir / f"{source_path.stem}_OCR.txt"
    if candidate.exists() and candidate.is_file():
        return candidate

    return None


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _excerpt(text: str, limit: int = 260) -> str:
    flat = re.sub(r"\s+", " ", text or "").strip()
    if len(flat) <= limit:
        return flat
    return f"{flat[: limit - 1].rstrip()}..."


def _normalize_ymd(year: str, month: str, day: str) -> str:
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def _extract_primary_date(text: str, filename: str) -> Optional[str]:
    filename_text = filename.replace("_", " ").replace("-", " ")
    content_text = text or ""

    match = re.search(r"\b(20\d{2})[-_/](\d{1,2})[-_/](\d{1,2})\b", filename)
    if match:
        return _normalize_ymd(match.group(1), match.group(2), match.group(3))

    month_pattern = "|".join(MONTHS)
    match = re.search(
        rf"\b({month_pattern})[\s_-]+(\d{{1,2}})(?:st|nd|rd|th)?(?:[\s,_-]+)(20\d{{2}})\b",
        filename_text,
        flags=re.IGNORECASE,
    )
    if match:
        return _normalize_ymd(match.group(3), MONTHS[match.group(1).lower()], match.group(2))

    match = re.search(
        rf"\b({month_pattern})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,\s*|\s+)(20\d{{2}})\b",
        content_text,
        flags=re.IGNORECASE,
    )
    if match:
        return _normalize_ymd(match.group(3), MONTHS[match.group(1).lower()], match.group(2))

    match = re.search(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", content_text)
    if match:
        return _normalize_ymd(match.group(1), match.group(2), match.group(3))

    match = re.search(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b", content_text)
    if match:
        return _normalize_ymd(match.group(3), match.group(1), match.group(2))

    return None


def _matched_issue_tags(text: str, filename: str) -> list[str]:
    haystack = f"{filename}\n{text or ''}".lower()
    matches = []
    for tag, terms in ISSUE_TERMS.items():
        if any(term.lower() in haystack for term in terms):
            matches.append(tag)
    return matches


def _classify_document(text: str, filename: str, suffix: str) -> str:
    haystack = f"{filename}\n{text or ''}".lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", haystack)
    if "ourfamilywizard" in normalized or "message report" in normalized:
        return "ofw_export"
    if (
        "support agreement" in normalized
        or "support agrement" in normalized
        or "support payment agreement" in normalized
    ):
        return "support_agreement"
    if "amendments to separation agreement" in normalized or "amendment" in normalized:
        return "agreement_amendment"
    if "seperation agreement" in normalized or "separation agreement" in normalized:
        return "agreement"
    if "bcfma" in normalized or "family maintenance" in normalized:
        return "support_payment"
    if "consent order" in normalized or "court file no" in normalized or "supreme court" in normalized:
        return "court_order_or_filing"
    if "parenting agreement" in normalized:
        return "agreement"
    if any(term in normalized for term in ["raymer", "rcmp", "exchange", "attendance"]):
        return "attendance_exchange"
    if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
        return "image_evidence"

    return classify_text(haystack).lower()


def _build_proof_gap_report(
    case_id: str,
    generated_at: str,
    manifest_rows: list[dict],
    timeline_rows: list[dict],
    duplicate_hash_groups: list[dict],
) -> str:
    lines = [
        f"# Proof Gap Report - {case_id}",
        "",
        f"Generated: {generated_at}",
        "",
        "This is an intake triage report. It flags what the file set appears to contain and what still needs source review.",
        "",
        "## Intake Summary",
        "",
        f"- Files reviewed: {len(manifest_rows)}",
        f"- Timeline rows drafted: {len(timeline_rows)}",
        "",
        "## Issue Coverage",
        "",
    ]

    for tag in ISSUE_TERMS:
        matching = [row for row in manifest_rows if tag in row["matched_issue_tags"].split(";")]
        status = "present" if matching else "missing"
        lines.append(f"- {tag}: {status} ({len(matching)} file(s))")

    no_text = [row for row in manifest_rows if row["extraction_status"] != "text_extracted"]
    unsorted = [row for row in manifest_rows if row["category"] in {"unsorted", "image_evidence"}]

    lines.extend(["", "## Needs Review", ""])
    if no_text:
        lines.append("Files with no extracted text:")
        for row in no_text[:20]:
            lines.append(f"- {row['intake_id']}: {row['original_filename']}")
    else:
        lines.append("- No no-text files detected in this intake.")

    lines.extend(["", "Unsorted or image-only files to manually inspect:"])
    if unsorted:
        for row in unsorted[:20]:
            lines.append(f"- {row['intake_id']}: {row['original_filename']}")
    else:
        lines.append("- No unsorted/image-only files detected in this intake.")

    lines.extend(["", "## Duplicate Hashes", ""])
    if duplicate_hash_groups:
        for group in duplicate_hash_groups:
            lines.append(f"- {group['sha256']}:")
            for item in group["files"]:
                lines.append(f"  - {item}")
    else:
        lines.append("- No exact duplicate file hashes detected in this intake.")

    lines.extend(
        [
            "",
            "## Suggested Next Checks",
            "",
            "- Confirm official/court-stamped documents before using any extracted text as filing support.",
            "- Compare timeline rows against the source PDFs or DOCXs before relying on dates.",
            "- Add missing source files for any issue marked missing above if that issue matters to the package.",
        ]
    )

    return "\n".join(lines) + "\n"


def _archive_output(output_dir: Path, archive_path: Path) -> None:
    if archive_path.exists():
        archive_path.unlink()

    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output_dir.rglob("*")):
            if not path.is_file() or path == archive_path:
                continue
            archive.write(path, path.relative_to(output_dir))


def run_case_intake(
    case_id: str,
    source_folder: Optional[Path] = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    recursive: bool = True,
    include_ext: Optional[set[str]] = None,
    source_files: Optional[list[Path]] = None,
    run_label: Optional[str] = None,
    ocr_scanned_pdfs: bool = False,
    ocr_text_dir: Optional[Path] = None,
    prefer_ocr_sidecar: bool = False,
    max_pdf_pages: int = 25,
) -> IntakeResult:
    if source_folder is not None:
        source_folder = Path(source_folder).expanduser().resolve()
        if not source_folder.exists() or not source_folder.is_dir():
            raise FileNotFoundError(f"Source folder not found: {source_folder}")

    include_ext = include_ext or SUPPORTED_EXTENSIONS
    output_root = Path(output_root).expanduser().resolve()
    if ocr_text_dir is not None:
        ocr_text_dir = Path(ocr_text_dir).expanduser().resolve()
        if not ocr_text_dir.exists() or not ocr_text_dir.is_dir():
            raise FileNotFoundError(f"OCR text folder not found: {ocr_text_dir}")

    label = run_label or f"case_intake_{_slugify(case_id)}_{_timestamp()}"
    output_dir = output_root / label

    source_copy_dir = output_dir / "source_files"
    extracted_text_dir = output_dir / "extracted_text"
    source_copy_dir.mkdir(parents=True, exist_ok=True)
    extracted_text_dir.mkdir(parents=True, exist_ok=True)

    files = _collect_source_files(
        source_folder=source_folder,
        source_files=source_files,
        recursive=recursive,
        include_ext=include_ext,
    )
    if not files:
        raise ValueError("No supported source files found")

    generated_at = _utc_now()
    manifest_rows: list[dict] = []
    timeline_rows: list[dict] = []

    for index, source_path in enumerate(files, start=1):
        intake_id = f"doc_{index:03d}"
        copied_path = source_copy_dir / _safe_filename(index, source_path)
        shutil.copy2(source_path, copied_path)

        ocr_sidecar = _find_ocr_sidecar(source_path, ocr_text_dir)
        text = safe_extract_text(
            str(copied_path),
            enable_pdf_ocr=ocr_scanned_pdfs,
            max_pdf_pages=max_pdf_pages,
        )
        sidecar_used = False
        if ocr_sidecar is not None and (prefer_ocr_sidecar or not text.strip()):
            text = ocr_sidecar.read_text(encoding="utf-8", errors="ignore").strip()
            sidecar_used = True

        text_path = extracted_text_dir / f"{intake_id}.txt"
        text_path.write_text(text, encoding="utf-8")

        source_hash = _sha256(source_path)
        copied_hash = _sha256(copied_path)
        tags = _matched_issue_tags(text, source_path.name)
        primary_date = _extract_primary_date(text, source_path.name)
        category = _classify_document(text, source_path.name, source_path.suffix.lower())
        extraction_status = "text_extracted" if text.strip() else "no_text"
        warnings = []
        if source_hash != copied_hash:
            warnings.append("copied_hash_mismatch")
        if sidecar_used:
            warnings.append("ocr_text_sidecar_used")
            if prefer_ocr_sidecar:
                warnings.append("ocr_text_sidecar_preferred")
        if not text.strip():
            warnings.append("no_text_extracted")
            if source_path.suffix.lower() == ".pdf" and not ocr_scanned_pdfs:
                warnings.append("scanned_pdf_ocr_not_enabled")
        if not primary_date:
            warnings.append("no_date_detected")

        stat = source_path.stat()
        manifest_rows.append(
            {
                "intake_id": intake_id,
                "case_id": case_id,
                "original_filename": source_path.name,
                "source_path": str(source_path),
                "copied_path": str(copied_path),
                "text_path": str(text_path),
                "ocr_sidecar_path": str(ocr_sidecar) if ocr_sidecar is not None else "",
                "source_sha256": source_hash,
                "copied_sha256": copied_hash,
                "size_bytes": stat.st_size,
                "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                "extension": source_path.suffix.lower(),
                "category": category,
                "primary_date": primary_date or "",
                "matched_issue_tags": ";".join(tags),
                "text_chars": len(text),
                "extraction_status": extraction_status,
                "warnings": ";".join(warnings),
            }
        )

        timeline_rows.append(
            {
                "date": primary_date or "",
                "intake_id": intake_id,
                "category": category,
                "title": source_path.name,
                "summary": _excerpt(text) or f"No text extracted from {source_path.name}",
                "source_path": str(source_path),
            "copied_path": str(copied_path),
            "text_path": str(text_path),
            "ocr_sidecar_path": str(ocr_sidecar) if ocr_sidecar is not None else "",
            "matched_issue_tags": ";".join(tags),
                "confidence": "source_copy_hash_verified" if source_hash == copied_hash else "copy_warning",
            }
        )

    timeline_rows.sort(key=lambda row: (row["date"] or "9999-12-31", row["title"].lower()))

    manifest_path = output_dir / "manifest.csv"
    timeline_csv_path = output_dir / "timeline.csv"
    timeline_json_path = output_dir / "timeline.json"
    proof_gaps_path = output_dir / "proof_gaps.md"
    dashboard_path = output_dir / "dashboard.json"
    archive_path = output_dir / f"{output_dir.name}.zip"

    hash_groups: dict[str, list[str]] = {}
    for row in manifest_rows:
        hash_groups.setdefault(row["source_sha256"], []).append(row["original_filename"])
    duplicate_hash_groups = [
        {"sha256": digest, "files": sorted(names)}
        for digest, names in sorted(hash_groups.items())
        if len(names) > 1
    ]

    _write_csv(
        manifest_path,
        manifest_rows,
        [
            "intake_id",
            "case_id",
            "original_filename",
            "source_path",
            "copied_path",
            "text_path",
            "ocr_sidecar_path",
            "source_sha256",
            "copied_sha256",
            "size_bytes",
            "modified_time",
            "extension",
            "category",
            "primary_date",
            "matched_issue_tags",
            "text_chars",
            "extraction_status",
            "warnings",
        ],
    )
    _write_csv(
        timeline_csv_path,
        timeline_rows,
        [
            "date",
            "intake_id",
            "category",
            "title",
            "summary",
            "source_path",
            "copied_path",
            "text_path",
            "ocr_sidecar_path",
            "matched_issue_tags",
            "confidence",
        ],
    )

    timeline_json_path.write_text(json.dumps(timeline_rows, indent=2), encoding="utf-8")
    proof_gaps_path.write_text(
        _build_proof_gap_report(
            case_id,
            generated_at,
            manifest_rows,
            timeline_rows,
            duplicate_hash_groups,
        ),
        encoding="utf-8",
    )

    dashboard = {
        "case_id": case_id,
        "generated_at": generated_at,
        "source_folder": str(source_folder) if source_folder is not None else None,
        "source_files": [str(path) for path in files],
        "ocr_text_dir": str(ocr_text_dir) if ocr_text_dir is not None else None,
        "output_dir": str(output_dir),
        "artifacts": {
            "manifest_csv": str(manifest_path),
            "timeline_csv": str(timeline_csv_path),
            "timeline_json": str(timeline_json_path),
            "proof_gaps_md": str(proof_gaps_path),
            "archive_zip": str(archive_path),
        },
        "counts": {
            "files": len(manifest_rows),
            "timeline_rows": len(timeline_rows),
            "with_text": sum(1 for row in manifest_rows if row["extraction_status"] == "text_extracted"),
            "without_text": sum(1 for row in manifest_rows if row["extraction_status"] != "text_extracted"),
            "duplicate_hash_groups": len(duplicate_hash_groups),
        },
        "duplicate_hash_groups": duplicate_hash_groups,
        "categories": {
            category: sum(1 for row in manifest_rows if row["category"] == category)
            for category in sorted({row["category"] for row in manifest_rows})
        },
        "issue_coverage": {
            tag: sum(1 for row in manifest_rows if tag in row["matched_issue_tags"].split(";"))
            for tag in ISSUE_TERMS
        },
    }
    dashboard_path.write_text(json.dumps(dashboard, indent=2), encoding="utf-8")

    _archive_output(output_dir, archive_path)

    return IntakeResult(
        output_dir=output_dir,
        manifest_path=manifest_path,
        timeline_csv_path=timeline_csv_path,
        timeline_json_path=timeline_json_path,
        proof_gaps_path=proof_gaps_path,
        dashboard_path=dashboard_path,
        archive_path=archive_path,
        file_count=len(manifest_rows),
    )
