from fastapi.testclient import TestClient

from src.case_intelligence import CASE_PEOPLE, sha256_bytes
from src.main import app

client = TestClient(app)


def test_case_people_are_seeded():
    response = client.get("/api/v1/cases/BCSC-138865/people")
    assert response.status_code == 200
    people = response.json()
    assert len(people) == 4
    names = {person["canonical_name"] for person in people}
    assert "Lindsay Alene McClean" in names
    assert "Clayton Miller" in names
    assert "Mitchel Watson" in names
    assert "Sofia Rae Watson" in names


def test_counsel_relationship_is_explicit():
    clayton = next(person for person in CASE_PEOPLE if person.person_id == "person_clayton_miller")
    assert clayton.represents_person_id == "person_lindsay_alene_mcclean"


def test_child_entity_is_protected():
    sofia = next(person for person in CASE_PEOPLE if person.person_id == "person_sofia_rae_watson")
    assert sofia.protected_minor is True


def test_sha256_is_stable():
    assert sha256_bytes(b"evidence") == "ee8250fb76e094b34b471f13a73dbbe51d1ae142e9df59d7c0d31ec20f0a0a8e"
