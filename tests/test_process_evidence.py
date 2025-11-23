import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient
from src.main import app


client = TestClient(app)

def test_process_evidence_happy_path():
    payload = {
        "case_id": "test-case-001",
        "items": [
            {
                "id": "item-001",
                "source": "sms",
                "content": "This is a sample sms text message about parenting.",
                "media_path": "/Users/mitchelwatson/Mitchopolis/parenting_evidence/inbox/example.txt",
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

def test_process_evidence_validation_error():
    bad_payload = {"items": []}
    response = client.post("/api/evidence/process", json=bad_payload)
    assert response.status_code == 422


def test_process_evidence_uses_ocr_when_available(monkeypatch):
    import src.router as router

    def mock_ocr(path):
        return "Extracted OCR text"

    monkeypatch.setattr(router, "safe_extract_text", mock_ocr)

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
    assert event["predicted_type"] == "UNSORTED"
