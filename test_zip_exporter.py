from src.utils import zip_exporter
from src.utils.zip_exporter import generate_evidence_zip


def test_zip_creation(tmp_path, monkeypatch):
    test_folder = tmp_path / "text_logs"
    test_folder.mkdir()
    (test_folder / "evidence.txt").write_text("evidence", encoding="utf-8")
    monkeypatch.setattr(zip_exporter, "EXPORT_ROOT", tmp_path / "exports")

    zip_path = generate_evidence_zip(test_folder)

    assert zip_path.exists(), "ZIP file was not created"
    assert zip_path.parent == tmp_path / "exports"
