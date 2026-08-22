import hashlib
import json

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from .case_intelligence import (
    CASE_ID,
    CASE_PEOPLE,
    Assertion,
    OFWCallEvent,
    OFWMessage,
    Person,
)
from .db import db
from .storage_contracts import ensure_unique_key_index

router = APIRouter(prefix="/api/v1", tags=["Case Intelligence"])
PERSON_BY_ID = {person.person_id: person for person in CASE_PEOPLE}


def _to_response(model: BaseModel) -> dict:
    return model.model_dump(mode="json")


def _require_known_case(case_id: str) -> None:
    if case_id != CASE_ID:
        raise HTTPException(status_code=404, detail="case not found")


def _require_known_person(person_id: str) -> Person:
    person = PERSON_BY_ID.get(person_id)
    if person is None:
        raise HTTPException(status_code=400, detail=f"unknown person_id: {person_id}")
    return person


def _fingerprint(model: BaseModel) -> str:
    canonical = json.dumps(
        model.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _persist_immutable(collection, key: dict, model: BaseModel, response: Response) -> dict:
    ensure_unique_key_index(collection, tuple(key))
    record_fingerprint = _fingerprint(model)
    payload = model.model_dump(mode="python")
    payload["_record_fingerprint"] = record_fingerprint
    try:
        result = collection.update_one(key, {"$setOnInsert": payload}, upsert=True)
    except DuplicateKeyError:
        result = None
    stored = collection.find_one(key, {"_id": 0})
    if stored is None:
        raise HTTPException(status_code=500, detail="record was not persisted")
    if stored.get("_record_fingerprint") != record_fingerprint:
        raise HTTPException(status_code=409, detail="identifier already exists with different content")
    response.status_code = 201 if result is not None and result.upserted_id is not None else 200
    stored.pop("_record_fingerprint", None)
    return stored


@router.get("/cases/{case_id}/people", response_model=list[Person])
def list_people(case_id: str):
    _require_known_case(case_id)
    return [_to_response(person) for person in CASE_PEOPLE]


@router.get("/cases/{case_id}/people/{person_id}", response_model=Person)
def get_person(case_id: str, person_id: str):
    _require_known_case(case_id)
    person = PERSON_BY_ID.get(person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="person not found")
    return _to_response(person)


@router.post("/cases/{case_id}/ofw/messages", response_model=OFWMessage, status_code=201)
def ingest_ofw_message(case_id: str, message: OFWMessage, response: Response):
    _require_known_case(case_id)
    if case_id != message.case_id:
        raise HTTPException(status_code=400, detail="case_id mismatch")
    _require_known_person(message.sender_person_id)
    for recipient_person_id in message.recipient_person_ids:
        _require_known_person(recipient_person_id)
    return _persist_immutable(
        db.ofw_messages,
        {"case_id": case_id, "message_id": message.message_id},
        message,
        response,
    )


@router.get("/cases/{case_id}/ofw/messages", response_model=list[OFWMessage])
def list_ofw_messages(case_id: str):
    _require_known_case(case_id)
    return list(
        db.ofw_messages.find({"case_id": case_id}, {"_id": 0, "_record_fingerprint": 0})
        .sort([("sent_at", 1), ("message_id", 1)])
    )


@router.post("/cases/{case_id}/ofw/calls", response_model=OFWCallEvent, status_code=201)
def ingest_ofw_call(case_id: str, event: OFWCallEvent, response: Response):
    _require_known_case(case_id)
    if case_id != event.case_id:
        raise HTTPException(status_code=400, detail="case_id mismatch")
    _require_known_person(event.caller_person_id)
    if event.related_child_person_id is not None:
        child = _require_known_person(event.related_child_person_id)
        if child.role != "child":
            raise HTTPException(status_code=400, detail="related_child_person_id is not a child")
    return _persist_immutable(
        db.ofw_call_events,
        {"case_id": case_id, "event_id": event.event_id},
        event,
        response,
    )


@router.post("/cases/{case_id}/assertions", response_model=Assertion, status_code=201)
def create_assertion(case_id: str, assertion: Assertion, response: Response):
    _require_known_case(case_id)
    if case_id != assertion.case_id:
        raise HTTPException(status_code=400, detail="case_id mismatch")
    _require_known_person(assertion.speaker_person_id)
    if assertion.human_verified or assertion.status in {"corroborated", "court_finding"}:
        raise HTTPException(
            status_code=400,
            detail="verification and court findings require a separate verified workflow",
        )
    return _persist_immutable(
        db.assertions,
        {"case_id": case_id, "assertion_id": assertion.assertion_id},
        assertion,
        response,
    )


@router.get(
    "/cases/{case_id}/people/{person_id}/assertions",
    response_model=list[Assertion],
)
def list_person_assertions(case_id: str, person_id: str):
    _require_known_case(case_id)
    _require_known_person(person_id)
    query = {"case_id": case_id, "speaker_person_id": person_id}
    return list(db.assertions.find(query, {"_id": 0, "_record_fingerprint": 0}))
