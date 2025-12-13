import tempfile
import os
import io
import zipfile
from pathlib import Path
from urllib.parse import quote

from fastapi.testclient import TestClient

from src.main import app


def create_sample_files(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    (root / "a.txt").write_text("hello")
    (root / "sub").mkdir(exist_ok=True)
    (root / "sub" / "b.txt").write_text("world")


def test_export_endpoint_creates_zip(tmp_path, monkeypatch):
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
