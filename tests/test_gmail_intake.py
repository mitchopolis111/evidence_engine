import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient

from src.main import app
from src.ocr import TextExtractionResult


client = TestClient(app)


def test_gmail_intake_preserves_attachment_provenance(tmp_path, monkeypatch):
    import src.router as router

    source_file = tmp_path / "Notice of Withdrawal of Lawyer (JCC for MW).pdf"
    source_file.write_bytes(b"%PDF-1.4\nsample")

    monkeypatch.setattr(
        router,
        "extract_text_with_diagnostics",
        lambda path: TextExtractionResult(
            text="Court File No.: 138865\nNOTICE OF WITHDRAWAL AS LAWYER",
            method="pdf_text",
        ),
    )

    payload = {
        "case_id": "BCSC_138865_Watson_v_McClean",
        "tags": ["court", "support"],
        "attachments": [
            {
                "thread_id": "thread-chandler-withdrawal",
                "thread_subject": "McClean v. Watson - ET Client",
                "message_id": "19c719f431b86633",
                "attachment_id": "att-notice-withdrawal",
                "filename": source_file.name,
                "media_path": str(source_file),
                "mime_type": "application/pdf",
                "size_bytes": 103800,
                "email_ts": "2026-02-18T16:39:44",
                "from": "Chantelle Akerstrom <Chantelle@chandlerlaw.ca>",
                "to": ["Mitchel Watson <mitchelwatson11@gmail.com>"],
                "cc": ["John Chandler <john@chandlerlaw.ca>"],
                "subject": "RE: McClean v. Watson - ET Client",
                "snippet": "Please see attached filed notice of withdrawal.",
                "display_url": "https://mail.google.com/mail/#all/19c719f431b86633",
                "labels": ["Legal/Lawyers/Chandler_Law"],
                "source_label": "Legal/Lawyers/Chandler_Law",
                "law_firm": "chandler_law",
            }
        ],
    }

    response = client.post("/api/evidence/gmail/intake", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == payload["case_id"]
    assert data["classified_count"] == 1

    event = data["timeline"][0]
    assert event["ocr_used"] is True
    assert event["extraction_method"] == "pdf_text"
    assert event["processing_warnings"] == []
    assert event["source_metadata"]["source"] == "gmail"
    assert event["source_metadata"]["thread_id"] == "thread-chandler-withdrawal"
    assert event["source_metadata"]["thread_subject"] == "McClean v. Watson - ET Client"
    assert event["source_metadata"]["message_id"] == "19c719f431b86633"
    assert event["source_metadata"]["subject"] == "RE: McClean v. Watson - ET Client"
    assert event["source_metadata"]["source_label"] == "Legal/Lawyers/Chandler_Law"
    assert event["source_metadata"]["law_firm"] == "chandler_law"
    assert event["source_metadata"]["attachment"]["attachment_id"] == "att-notice-withdrawal"
    assert event["source_metadata"]["attachment"]["filename"] == source_file.name


def test_process_evidence_accepts_source_metadata():
    payload = {
        "case_id": "test-case-source-metadata",
        "items": [
            {
                "id": "item-with-email-source",
                "source": "gmail",
                "content": "Document served on 2025-10-01.",
                "media_path": None,
                "tags": ["gmail"],
                "source_metadata": {
                    "thread_id": "thread-oct-1",
                    "message_id": "message-oct-1",
                    "attachment": {"filename": "court-document.pdf"},
                },
            }
        ],
    }

    response = client.post("/api/evidence/process", json=payload)

    assert response.status_code == 200
    event = response.json()["timeline"][0]
    assert event["source_metadata"]["thread_id"] == "thread-oct-1"
    assert event["source_metadata"]["attachment"]["filename"] == "court-document.pdf"


def test_gmail_intake_accepts_metadata_only_attachment():
    payload = {
        "case_id": "BCSC_138865_Watson_v_McClean",
        "attachments": [
            {
                "message_id": "18c33019907afd46",
                "thread_subject": "Re: Documents",
                "filename": "4 Affidavit 1 of L. McClean, filed Nov 21, 2023.pdf",
                "mime_type": "application/pdf",
                "size_bytes": 7498621,
                "subject": "Re: Documents",
                "source_label": "Legal/Lawyers/Porterramsay_Law",
                "law_firm": "porterramsay_law",
            }
        ],
    }

    response = client.post("/api/evidence/gmail/intake", json=payload)

    assert response.status_code == 200
    event = response.json()["timeline"][0]
    assert event["ocr_used"] is False
    assert event["source_metadata"]["law_firm"] == "porterramsay_law"
    assert (
        event["source_metadata"]["attachment"]["filename"]
        == "4 Affidavit 1 of L. McClean, filed Nov 21, 2023.pdf"
    )
