from src.utils import zip_exporter
from src.utils.court_bundle import build_court_bundle


def test_build_court_bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(zip_exporter, "EXPORT_ROOT", tmp_path / "exports")
    monkeypatch.setattr(zip_exporter, "TMP_DIR", tmp_path / "exports" / "tmp")

    test_folder = tmp_path / "text_logs"
    test_folder.mkdir()
    (test_folder / "sample.txt").write_text("sample evidence", encoding="utf-8")

    zip_path = build_court_bundle("test_case", test_folder)
    assert zip_path.exists(), "Bundle ZIP was not created"
