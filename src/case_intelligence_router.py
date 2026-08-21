from fastapi import APIRouter, HTTPException

from .case_intelligence import CASE_ID, CASE_PEOPLE, Assertion, OFWCallEvent, OFWMessage
from .db import db

router = APIRouter(prefix="/api/v1", tags=["Case Intelligence"])


def _serialize(model):
    return model.model_dump(mode="json")


@router.get("/cases/{case_id}/people")
def list_people(case_id: str):
    if case_id != CASE_ID:
        return []
    return [_serialize(person) for person in CASE_PEOPLE]


@router.get("/cases/{case_id}/people/{person_id}")
def get_person(case_id: str, person_id: str):
    for person in CASE_PEOPLE:
        if person.case_id == case_id and person.person_id == person_id:
            return _serialize(person)
    raise HTTPException(status_code=404, detail="person not found")


@router.post("/cases/{case_id}/ofw/messages", status_code=201)
def ingest_ofw_message(case_id: str, message: OFWMessage):
    if case_id != message.case_id:
        raise HTTPException(status_code=400, detail="case_id mismatch")
    payload = _serialize(message)
    db.ofw_messages.update_one(
        {"case_id": case_id, "message_id": message.message_id},
        {"$setOnInsert": payload},
        upsert=True,
    )
    return payload


@router.get("/cases/{case_id}/ofw/messages")
def list_ofw_messages(case_id: str):
    return list(db.ofw_messages.find({"case_id": case_id}, {"_id": 0}).sort("sent_at", 1))


@router.post("/cases/{case_id}/ofw/calls", status_code=201)
def ingest_ofw_call(case_id: str, event: OFWCallEvent):
    if case_id != event.case_id:
        raise HTTPException(status_code=400, detail="case_id mismatch")
    payload = _serialize(event)
    db.ofw_call_events.update_one(
        {"case_id": case_id, "event_id": event.event_id},
        {"$setOnInsert": payload},
        upsert=True,
    )
    return payload


@router.post("/cases/{case_id}/assertions", status_code=201)
def create_assertion(case_id: str, assertion: Assertion):
    if case_id != assertion.case_id:
        raise HTTPException(status_code=400, detail="case_id mismatch")
    payload = _serialize(assertion)
    db.assertions.update_one(
        {"case_id": case_id, "assertion_id": assertion.assertion_id},
        {"$set": payload},
        upsert=True,
    )
    return payload


@router.get("/cases/{case_id}/people/{person_id}/assertions")
def list_person_assertions(case_id: str, person_id: str):
    query = {"case_id": case_id, "speaker_person_id": person_id}
    return list(db.assertions.find(query, {"_id": 0}))
