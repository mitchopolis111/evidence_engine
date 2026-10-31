from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import src.case_intelligence_router as intelligence_router
from src.main import app
from tests.fakes import FakeCollection

client = TestClient(app)


def fake_database():
    return SimpleNamespace(
        ofw_messages=FakeCollection(),
        ofw_call_events=FakeCollection(),
        assertions=FakeCollection(),
    )


def message_payload():
    return {
        "message_id": "ofw_test_message",
        "case_id": "BCSC-138865",
        "sender_person_id": "person_mitchel_watson",
        "recipient_person_ids": ["person_lindsay_alene_mcclean"],
        "sent_at": "2026-07-10T15:27:00-07:00",
        "sent_at_raw": "07/10/2026 3:27 PM",
        "source_timezone": "America/Vancouver",
        "subject": "Test",
        "body": "Evidence body",
        "source": {
            "document_id": "doc-1",
            "sha256": "a" * 64,
            "record_locator": "message:1/1",
            "source_type": "ofw_message_report",
            "extraction_method": "native",
        },
    }


def test_message_post_is_idempotent_and_conflicts_fail_closed(monkeypatch):
    fake_db = fake_database()
    monkeypatch.setattr(intelligence_router, "db", fake_db)
    payload = message_payload()

    created = client.post("/api/v1/cases/BCSC-138865/ofw/messages", json=payload)
    replayed = client.post("/api/v1/cases/BCSC-138865/ofw/messages", json=payload)
    conflicting_payload = {**payload, "body": "Changed evidence body"}
    conflicting = client.post(
        "/api/v1/cases/BCSC-138865/ofw/messages",
        json=conflicting_payload,
    )

    assert created.status_code == 201
    assert replayed.status_code == 200
    assert conflicting.status_code == 409
    assert len(fake_db.ofw_messages.documents) == 1
    stored = next(iter(fake_db.ofw_messages.documents.values()))
    assert isinstance(stored["sent_at"], datetime)
    assert created.json()["body"] == "Evidence body"
    assert fake_db.ofw_messages.indexes[0][1]["unique"] is True
    assert fake_db.ofw_messages.indexes[0][1]["name"] == "uq_case_id_message_id"


def test_unknown_case_returns_not_found():
    response = client.get("/api/v1/cases/not-a-case/people")

    assert response.status_code == 404


def test_assertions_cannot_self_declare_human_verification(monkeypatch):
    monkeypatch.setattr(intelligence_router, "db", fake_database())
    payload = {
        "assertion_id": "assertion-1",
        "case_id": "BCSC-138865",
        "speaker_person_id": "person_lindsay_alene_mcclean",
        "normalized_claim": "Example claim",
        "human_verified": True,
        "source": {
            "document_id": "doc-1",
            "sha256": "b" * 64,
            "source_type": "affidavit",
            "extraction_method": "native",
        },
    }

    response = client.post("/api/v1/cases/BCSC-138865/assertions", json=payload)

    assert response.status_code == 400


@pytest.mark.parametrize("status", ["corroborated", "court_finding"])
def test_assertions_cannot_self_declare_privileged_status(monkeypatch, status):
    monkeypatch.setattr(intelligence_router, "db", fake_database())
    payload = {
        "assertion_id": "assertion-1",
        "case_id": "BCSC-138865",
        "speaker_person_id": "person_lindsay_alene_mcclean",
        "normalized_claim": "Example claim",
        "status": status,
        "source": {
            "document_id": "doc-1",
            "sha256": "b" * 64,
            "source_type": "affidavit",
            "extraction_method": "native",
        },
    }

    response = client.post("/api/v1/cases/BCSC-138865/assertions", json=payload)

    assert response.status_code == 400


def test_openapi_exposes_typed_case_intelligence_contracts():
    schema = client.get("/openapi.json").json()
    required_paths = {
        "/api/v1/cases/{case_id}/people",
        "/api/v1/cases/{case_id}/ofw/messages",
        "/api/v1/cases/{case_id}/ofw/calls",
        "/api/v1/cases/{case_id}/assertions",
    }

    assert required_paths <= schema["paths"].keys()
    message_response = schema["paths"]["/api/v1/cases/{case_id}/ofw/messages"]["post"]["responses"]["201"]
    assert "$ref" in message_response["content"]["application/json"]["schema"]
