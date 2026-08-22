import zipfile

from src.utils import zip_exporter


def test_generate_evidence_zip_delegates_to_canonical_exporter(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "evidence.txt").write_text("evidence", encoding="utf-8")
    monkeypatch.setattr(zip_exporter, "EXPORT_ROOT", tmp_path / "exports")

    archive = zip_exporter.generate_evidence_zip(source)

    assert archive.name == "source_export.zip"
    with zipfile.ZipFile(archive) as exported:
        assert exported.namelist() == ["evidence.txt"]
