import sys
import os

# Ensure src is on path, same approach as other tests
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)


def test_ingest_evidence_happy_path():
    payload = {
        "case_id": "test-case-ingest-001",
        "items": [
            {
                "id": "item-001",
                "source": "sms",
                "content": "This is a sample text message about parenting.",
                "media_path": None,
                "tags": ["sample", "test"],
            }
        ],
    }

    res = client.post("/api/evidence/ingest", json=payload)
    assert res.status_code == 200

    data = res.json()
    assert data["case_id"] == payload["case_id"]
    assert "timeline" in data
    assert len(data["timeline"]) == 1

    event = data["timeline"][0]
    # Summary should be based on content (no OCR)
    assert event["summary"].startswith(payload["items"][0]["content"][:10])
    assert data["classified_count"] == 1
