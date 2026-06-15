import csv
import json
import zipfile

from src.ocr import safe_extract_text
from src.utils.case_intake import run_case_intake


def _write_docx(path, text):
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>"
        f"{text}"
        "</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "")
        archive.writestr("word/document.xml", document_xml)


def test_safe_extract_text_reads_docx(tmp_path):
    source = tmp_path / "Agreement.docx"
    _write_docx(source, "Parenting Agreement, Dated December 29, 2024")

    assert "Parenting Agreement" in safe_extract_text(str(source))


def test_case_intake_builds_source_preserving_artifacts(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    text_file = source_dir / "OFW_Messages_Report.txt"
    text_file.write_text(
        "OurFamilyWizard Message Report\nSent: 01/03/2025 at 12:08 PM\nParenting time exchange.",
        encoding="utf-8",
    )
    docx_file = source_dir / "Consent_Order_filed_June_17_2024.docx"
    _write_docx(
        docx_file,
        "Supreme Court Consent Order Court File No. 138865 old form date 2015-11-01",
    )

    result = run_case_intake(
        case_id="BCSC_138865_Watson_v_McClean",
        source_folder=source_dir,
        output_root=tmp_path / "output",
        run_label="case_intake_test",
    )

    assert result.file_count == 2
    assert text_file.exists()
    assert docx_file.exists()
    assert result.manifest_path.exists()
    assert result.timeline_csv_path.exists()
    assert result.dashboard_path.exists()
    assert result.archive_path.exists()

    with result.manifest_path.open(encoding="utf-8") as handle:
        manifest_rows = list(csv.DictReader(handle))

    assert len(manifest_rows) == 2
    assert all(row["source_sha256"] == row["copied_sha256"] for row in manifest_rows)
    assert {row["extraction_status"] for row in manifest_rows} == {"text_extracted"}
    assert any(row["category"] == "ofw_export" for row in manifest_rows)
    assert any(row["category"] == "court_order_or_filing" for row in manifest_rows)

    timeline = json.loads(result.timeline_json_path.read_text(encoding="utf-8"))
    assert len(timeline) == 2
    assert any(row["date"] == "2025-01-03" for row in timeline)
    assert any(row["date"] == "2024-06-17" for row in timeline)

    dashboard = json.loads(result.dashboard_path.read_text(encoding="utf-8"))
    assert dashboard["counts"]["files"] == 2
    assert dashboard["issue_coverage"]["court_file_138865"] == 1

    with zipfile.ZipFile(result.archive_path) as archive:
        names = set(archive.namelist())

    assert "manifest.csv" in names
    assert "timeline.csv" in names
    assert "proof_gaps.md" in names
    assert "dashboard.json" in names


def test_case_intake_accepts_exact_source_files(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    selected = source_dir / "Agreement_Signed_Jan_20_2023_Support_Agreement_Filed.txt"
    selected.write_text("Support Agreement dated January 20, 2023", encoding="utf-8")
    ignored = source_dir / "ignored.txt"
    ignored.write_text("Consent Order dated June 17, 2024", encoding="utf-8")

    result = run_case_intake(
        case_id="BCSC_138865_Watson_v_McClean",
        source_folder=None,
        source_files=[selected],
        output_root=tmp_path / "output",
        run_label="exact_files",
    )

    with result.manifest_path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 1
    assert rows[0]["source_path"] == str(selected.resolve())
    assert rows[0]["category"] == "support_agreement"
    assert rows[0]["primary_date"] == "2023-01-20"


def test_case_intake_classifies_agreements_from_filename_when_no_text(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    support = source_dir / "Agreement_Signed_Jan_20_2023_Support_Agreement_Filed.txt"
    misspelled_support = source_dir / "Agreement_Signed_June_17_2024_Support_Agrement_Filed.txt"
    amendment = source_dir / "Agreement_Signed_Jan_6_2023_Amendments_To_Separation_Agreement_Filed.txt"
    separation = source_dir / "Agreement_Signed_Dec_14_2021_Seperation_Agreement_Filed.txt"
    for path in (support, misspelled_support, amendment, separation):
        path.write_text("", encoding="utf-8")

    result = run_case_intake(
        case_id="BCSC_138865_Watson_v_McClean",
        source_files=[support, misspelled_support, amendment, separation],
        output_root=tmp_path / "output",
        run_label="filename_only",
    )

    with result.manifest_path.open(encoding="utf-8") as handle:
        rows = {row["original_filename"]: row for row in csv.DictReader(handle)}

    assert rows[support.name]["category"] == "support_agreement"
    assert rows[misspelled_support.name]["category"] == "support_agreement"
    assert rows[amendment.name]["category"] == "agreement_amendment"
    assert rows[separation.name]["category"] == "agreement"
    assert rows[support.name]["primary_date"] == "2023-01-20"
    assert rows[misspelled_support.name]["primary_date"] == "2024-06-17"
    assert rows[amendment.name]["primary_date"] == "2023-01-06"
    assert rows[separation.name]["primary_date"] == "2021-12-14"


def test_case_intake_reports_duplicate_hash_groups(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    first = source_dir / "Consent_Order_filed_June_17_2024.txt"
    second = source_dir / "Agreement_Signed_June_17_2024_Support_Agrement_Filed.txt"
    for path in (first, second):
        path.write_text("Consent Order dated June 17, 2024", encoding="utf-8")

    result = run_case_intake(
        case_id="BCSC_138865_Watson_v_McClean",
        source_files=[first, second],
        output_root=tmp_path / "output",
        run_label="duplicates",
    )

    dashboard = json.loads(result.dashboard_path.read_text(encoding="utf-8"))
    assert dashboard["counts"]["duplicate_hash_groups"] == 1
    assert sorted(dashboard["duplicate_hash_groups"][0]["files"]) == sorted(
        [first.name, second.name]
    )
    assert "Duplicate Hashes" in result.proof_gaps_path.read_text(encoding="utf-8")


def test_case_intake_uses_ocr_text_sidecar_for_no_text_pdf(tmp_path, monkeypatch):
    import src.utils.case_intake as case_intake

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    ocr_dir = tmp_path / "ocr"
    ocr_dir.mkdir()
    pdf = source_dir / "Agreement_Signed_Jan_20_2023_Support_Agreement_Filed.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    sidecar = ocr_dir / "Agreement_Signed_Jan_20_2023_Support_Agreement_Filed_OCR.txt"
    sidecar.write_text("Support Agreement dated January 20, 2023", encoding="utf-8")
    monkeypatch.setattr(case_intake, "safe_extract_text", lambda *args, **kwargs: "")

    result = run_case_intake(
        case_id="BCSC_138865_Watson_v_McClean",
        source_files=[pdf],
        ocr_text_dir=ocr_dir,
        output_root=tmp_path / "output",
        run_label="sidecar",
    )

    with result.manifest_path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert rows[0]["extraction_status"] == "text_extracted"
    assert rows[0]["text_chars"] == str(len("Support Agreement dated January 20, 2023"))
    assert rows[0]["ocr_sidecar_path"] == str(sidecar.resolve())
    assert "ocr_text_sidecar_used" in rows[0]["warnings"]
    assert "Support Agreement" in result.timeline_csv_path.read_text(encoding="utf-8")


def test_case_intake_can_prefer_corrected_sidecar_over_embedded_text(tmp_path, monkeypatch):
    import src.utils.case_intake as case_intake

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    ocr_dir = tmp_path / "ocr"
    ocr_dir.mkdir()
    pdf = source_dir / "Agreement_Signed_Jan_20_2023_Support_Agreement_Filed.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    sidecar = ocr_dir / "Agreement_Signed_Jan_20_2023_Support_Agreement_Filed_OCR.txt"
    sidecar.write_text(
        "Corrected Support Agreement dated January 20, 2023 for $2,113",
        encoding="utf-8",
    )
    monkeypatch.setattr(case_intake, "safe_extract_text", lambda *args, **kwargs: "Bad OCR $ZH3")

    result = run_case_intake(
        case_id="BCSC_138865_Watson_v_McClean",
        source_files=[pdf],
        ocr_text_dir=ocr_dir,
        prefer_ocr_sidecar=True,
        output_root=tmp_path / "output",
        run_label="sidecar_override",
    )

    with result.manifest_path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    extracted_text = (result.output_dir / "extracted_text" / "doc_001.txt").read_text(encoding="utf-8")
    assert "$2,113" in extracted_text
    assert "$ZH3" not in extracted_text
    assert rows[0]["ocr_sidecar_path"] == str(sidecar.resolve())
    assert "ocr_text_sidecar_used" in rows[0]["warnings"]
    assert "ocr_text_sidecar_preferred" in rows[0]["warnings"]
