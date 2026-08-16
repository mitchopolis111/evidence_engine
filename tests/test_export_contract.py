import os
import zipfile
from pathlib import Path

import pytest

from src.utils import zip_exporter


def test_generate_evidence_zip_preserves_export_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(zip_exporter, "EXPORT_ROOT", tmp_path / "exports")
    monkeypatch.setattr(zip_exporter, "TMP_DIR", tmp_path / "exports" / "tmp")

    source = tmp_path / "source"
    source.mkdir()
    (source / "a.txt").write_text("hello", encoding="utf-8")
    (source / "sub").mkdir()
    (source / "sub" / "b.txt").write_text("world", encoding="utf-8")

    zip_path = zip_exporter.generate_evidence_zip(source)

    assert zip_path == tmp_path / "exports" / "source_export.zip"
    assert zip_path.exists()

    with zipfile.ZipFile(zip_path) as archive:
        names = sorted(archive.namelist())

    assert names == ["a.txt", "sub/b.txt"]
    assert all(not Path(name).is_absolute() for name in names)


def test_generate_evidence_zip_is_deterministic(tmp_path, monkeypatch):
    monkeypatch.setattr(zip_exporter, "EXPORT_ROOT", tmp_path / "exports")
    source = tmp_path / "source"
    source.mkdir()
    source_file = source / "evidence.txt"
    source_file.write_text("same evidence", encoding="utf-8")

    first_bytes = zip_exporter.generate_evidence_zip(source).read_bytes()
    os.utime(source_file, (1_800_000_000, 1_800_000_000))
    second_bytes = zip_exporter.generate_evidence_zip(source).read_bytes()

    assert second_bytes == first_bytes


def test_generate_evidence_zip_rejects_symlinks(tmp_path, monkeypatch):
    monkeypatch.setattr(zip_exporter, "EXPORT_ROOT", tmp_path / "exports")
    source = tmp_path / "source"
    source.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("not approved", encoding="utf-8")
    (source / "linked.txt").symlink_to(outside)

    with pytest.raises(zip_exporter.UnsafeExportPathError):
        zip_exporter.generate_evidence_zip(source)
