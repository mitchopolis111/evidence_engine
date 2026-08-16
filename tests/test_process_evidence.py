import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient
from src.main import app
from src.ocr import TextExtractionResult


client = TestClient(app)

def test_process_evidence_happy_path(tmp_path):
    payload = {
        "case_id": "test-case-001",
        "items": [
            {
                "id": "item-001",
                "source": "sms",
                "content": "This is a sample sms text message about parenting.",
                "media_path": str(tmp_path / "missing.txt"),
                "tags": ["sample", "test"]
            }
        ]
    }

    response = client.post("/api/evidence/process", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["case_id"] == payload["case_id"]
    assert "timeline" in data
    assert len(data["timeline"]) == 1

    event = data["timeline"][0]
    assert event["summary"] == payload["items"][0]["content"]
    assert event["evidence_ids"] == ["item-001"]
    assert event["timestamp"] is None
    assert event["predicted_type"] == "TEXTLOG"
    assert event["extraction_method"] == "provided_content_fallback"
    assert [warning["code"] for warning in event["processing_warnings"]] == [
        "media_not_found"
    ]

def test_process_evidence_validation_error():
    bad_payload = {"items": []}
    response = client.post("/api/evidence/process", json=bad_payload)
    assert response.status_code == 422


def test_process_evidence_uses_ocr_when_available(monkeypatch):
    import src.router as router

    def mock_ocr(path):
        return TextExtractionResult(
            text="Extracted OCR text",
            method="image_ocr",
        )

    monkeypatch.setattr(router, "extract_text_with_diagnostics", mock_ocr)

    payload = {
        "case_id": "test-case-002",
        "items": [
            {
                "id": "item-002",
                "source": "photo",
                "content": "original content that should be replaced",
                "media_path": "/fake/path/image.jpg",
                "tags": []
            }
        ],
    }

    response = client.post("/api/evidence/process", json=payload)
    assert response.status_code == 200

    data = response.json()
    event = data["timeline"][0]

    assert event["summary"] == "Extracted OCR text"
    assert event["ocr_used"] is True
    assert event["extraction_method"] == "image_ocr"
    assert event["processing_warnings"] == []
    assert event["predicted_type"] == "UNSORTED"


def test_process_evidence_reports_unsupported_media_type(tmp_path):
    source = tmp_path / "evidence.xyz"
    source.write_text("not supported", encoding="utf-8")
    payload = {
        "case_id": "test-case-unsupported-media",
        "items": [
            {
                "id": "item-unsupported-media",
                "source": "file",
                "content": "Fallback description",
                "media_path": str(source),
                "tags": [],
            }
        ],
    }

    response = client.post("/api/evidence/process", json=payload)

    assert response.status_code == 200
    event = response.json()["timeline"][0]
    assert event["summary"] == "Fallback description"
    assert event["extraction_method"] == "provided_content_fallback"
    assert [warning["code"] for warning in event["processing_warnings"]] == [
        "unsupported_media_type"
    ]


def test_process_evidence_reports_empty_media_extraction(tmp_path):
    source = tmp_path / "empty.txt"
    source.write_text("", encoding="utf-8")
    payload = {
        "case_id": "test-case-empty-extraction",
        "items": [
            {
                "id": "item-empty-extraction",
                "source": "file",
                "content": "Fallback description",
                "media_path": str(source),
                "tags": [],
            }
        ],
    }

    response = client.post("/api/evidence/process", json=payload)

    assert response.status_code == 200
    event = response.json()["timeline"][0]
    assert event["extraction_method"] == "provided_content_fallback"
    assert [warning["code"] for warning in event["processing_warnings"]] == [
        "no_text_extracted"
    ]


def test_process_evidence_extracts_timestamp_from_content():
    payload = {
        "case_id": "test-case-003",
        "items": [
            {
                "id": "item-003",
                "source": "sms",
                "content": "Incident on 2025-11-20 at 5pm, please review.",
                "media_path": None,
                "tags": [],
            }
        ],
    }

    response = client.post("/api/evidence/process", json=payload)
    assert response.status_code == 200

    event = response.json()["timeline"][0]
    assert event["timestamp"] == "2025-11-20"


def test_get_timeline_by_case_id():
    payload = {
        "case_id": "test-case-004",
        "items": [
            {
                "id": "item-004",
                "source": "sms",
                "content": "Timeline entry for 2025-11-21.",
                "media_path": None,
                "tags": [],
            }
        ],
    }

    post_res = client.post("/api/evidence/process", json=payload)
    assert post_res.status_code == 200

    get_res = client.get(f"/api/evidence/timeline/{payload['case_id']}")
    assert get_res.status_code == 200
    data = get_res.json()
    assert isinstance(data, list)
    assert data[0]["case_id"] == payload["case_id"]


def test_process_evidence_uses_memory_fallback_when_mongo_unavailable(monkeypatch):
    import src.router as router

    class UnavailableCollection:
        def bulk_write(self, ops, ordered=False):
            raise RuntimeError("mongo unavailable")

        def find(self, *args, **kwargs):
            raise RuntimeError("mongo unavailable")

    case_id = "test-case-mongo-fallback"
    router.CASE_TIMELINES.pop(case_id, None)
    monkeypatch.setattr(router, "get_collection", lambda name: UnavailableCollection())

    payload = {
        "case_id": case_id,
        "items": [
            {
                "id": "item-mongo-fallback",
                "source": "sms",
                "content": "Timeline fallback entry for 2025-11-22.",
                "media_path": None,
                "tags": [],
            }
        ],
    }

    post_res = client.post("/api/evidence/process", json=payload)
    assert post_res.status_code == 200

    get_res = client.get(f"/api/evidence/timeline/{case_id}")
    assert get_res.status_code == 200
    data = get_res.json()
    assert data[0]["case_id"] == case_id
    assert data[0]["evidence_ids"] == ["item-mongo-fallback"]
