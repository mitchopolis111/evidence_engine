import tempfile
import os
import io
import zipfile
from pathlib import Path
from urllib.parse import quote

from fastapi.testclient import TestClient

from src.main import app
from src.utils import zip_exporter


def create_sample_files(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    (root / "a.txt").write_text("hello")
    (root / "sub").mkdir(exist_ok=True)
    (root / "sub" / "b.txt").write_text("world")


def test_export_endpoint_creates_zip(tmp_path, monkeypatch):
    monkeypatch.setattr(zip_exporter, "EXPORT_ROOT", tmp_path / "exports")
    monkeypatch.setattr(zip_exporter, "TMP_DIR", tmp_path / "exports" / "tmp")
    monkeypatch.setenv("EVIDENCE_SOURCE_FOLDER", str(tmp_path))

    # Create a temporary source folder with sample files
    src_folder = tmp_path / "source"
    create_sample_files(src_folder)

    client = TestClient(app)

    # Call endpoint with folder query param (URL-encoded)
    url = f"/api/evidence/export?folder={quote(str(src_folder))}"
    resp = client.get(url)

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/zip")

    # Verify returned content is a zip and contains our files
    z = zipfile.ZipFile(io.BytesIO(resp.content))
    names = set(z.namelist())
    assert "a.txt" in names
    assert "sub/b.txt" in names


def test_export_endpoint_uses_configured_source_when_folder_is_omitted(
    tmp_path, monkeypatch
):
    source = tmp_path / "source"
    create_sample_files(source)
    monkeypatch.setenv("EVIDENCE_SOURCE_FOLDER", str(source))
    monkeypatch.setattr(zip_exporter, "EXPORT_ROOT", tmp_path / "exports")

    response = TestClient(app).get("/api/evidence/export")

    assert response.status_code == 200


def test_export_endpoint_rejects_folder_outside_approved_roots(
    tmp_path, monkeypatch
):
    approved = tmp_path / "approved"
    approved.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setenv("EVIDENCE_SOURCE_FOLDER", str(approved))

    response = TestClient(app).get(
        f"/api/evidence/export?folder={quote(str(outside))}"
    )

    assert response.status_code == 403


def test_export_endpoint_rejects_relative_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("EVIDENCE_SOURCE_FOLDER", str(tmp_path))

    response = TestClient(app).get("/api/evidence/export?folder=relative/path")

    assert response.status_code == 400


def test_export_endpoint_reports_missing_folder_inside_approved_root(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("EVIDENCE_SOURCE_FOLDER", str(tmp_path))
    missing = tmp_path / "missing"

    response = TestClient(app).get(
        f"/api/evidence/export?folder={quote(str(missing))}"
    )

    assert response.status_code == 404


def test_export_endpoint_rejects_symlink_escape(tmp_path, monkeypatch):
    approved = tmp_path / "approved"
    approved.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = approved / "linked"
    linked.symlink_to(outside, target_is_directory=True)
    monkeypatch.setenv("EVIDENCE_SOURCE_FOLDER", str(approved))

    response = TestClient(app).get(
        f"/api/evidence/export?folder={quote(str(linked))}"
    )

    assert response.status_code == 403
