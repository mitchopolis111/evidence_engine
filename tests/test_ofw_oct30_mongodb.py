import pytest

from src.ofw_import import OFWImportConflict, import_ofw_messages
from tests.ofw_mongo_server import isolated_mongo, mongo_collection  # noqa: F401
from tests.ofw_private_checks import private_export_checks
from tests.test_ofw_mongodb import concurrent_imports
from tests.test_ofw_oct16_export import oct16_export  # noqa: F401
from tests.test_ofw_oct30_export import assert_cross_report_records, oct30_export  # noqa: F401

pytestmark = [pytest.mark.mongodb, pytest.mark.real_export]


@pytest.mark.parametrize("reverse", [False, True])
@private_export_checks()
def test_live_cross_report_import_and_replay(mongo_collection, oct16_export, oct30_export, reverse):
    _, older = oct16_export
    _, newer = oct30_export
    reports = [newer, older] if reverse else [older, newer]
    results = [import_ofw_messages(mongo_collection, report) for report in reports]
    assert [r.inserted_count for r in results] == ([1174, 0] if reverse else [622, 552])
    assert [r.occurrence_added_count for r in results] == ([1174, 622] if reverse else [622, 1174])
    assert_cross_report_records(list(mongo_collection.find({})), older, newer)
    for report in reports:
        replay = import_ofw_messages(mongo_collection, report)
        assert (replay.inserted_count, replay.occurrence_added_count) == (0, 0)
    assert_cross_report_records(list(mongo_collection.find({})), older, newer)


@private_export_checks()
def test_eight_concurrent_overlapping_reports(mongo_collection, oct16_export, oct30_export):
    _, older = oct16_export
    _, newer = oct30_export
    reports = [older, newer] * 4
    results = concurrent_imports(mongo_collection, reports)
    assert sum(r.inserted_count for r in results) == 1174
    assert sum(r.occurrence_added_count for r in results) == 1796
    assert_cross_report_records(list(mongo_collection.find({})), older, newer)
    results = concurrent_imports(mongo_collection, reports)
    assert sum(r.inserted_count for r in results) == sum(r.occurrence_added_count for r in results) == 0
    assert_cross_report_records(list(mongo_collection.find({})), older, newer)


@private_export_checks()
def test_live_legacy_identity_guard_preserves_existing_records(mongo_collection, oct16_export, oct30_export):
    _, older = oct16_export
    _, newer = oct30_export
    legacy = [m.model_dump(mode="python") for m in older.messages]
    for record in legacy:
        record.pop("identity_version")
    mongo_collection.insert_many(legacy)
    before = list(mongo_collection.find({}))
    with pytest.raises(OFWImportConflict, match="legacy identity version"):
        import_ofw_messages(mongo_collection, newer)
    assert list(mongo_collection.find({})) == before
