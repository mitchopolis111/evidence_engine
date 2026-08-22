from zipfile import ZipFile

from src.utils.court_bundle import build_court_bundle


def test_build_court_bundle(tmp_path):
    test_folder = tmp_path / "text_logs"
    test_folder.mkdir()
    (test_folder / "message.txt").write_text("Example evidence", encoding="utf-8")

    zip_path = build_court_bundle("test_case", test_folder)

    assert zip_path.exists(), "Bundle ZIP was not created"
    with ZipFile(zip_path) as bundle:
        assert bundle.namelist() == ["message.txt"]
        assert bundle.read("message.txt") == b"Example evidence"


def test_build_court_bundle_preserves_dotted_folder_name(tmp_path):
    test_folder = tmp_path / "case.v1"
    test_folder.mkdir()

    zip_path = build_court_bundle("test_case", test_folder)

    assert zip_path == tmp_path / "case.v1.zip"
    assert zip_path.exists()
