import io
import zipfile
from pathlib import Path
from urllib.parse import quote
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from src.main import app


def create_sample_files(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    (root / "a.txt").write_text("hello")
    (root / "sub").mkdir(exist_ok=True)
    (root / "sub" / "b.txt").write_text("world")


def create_zip_bytes(folder: Path) -> bytes:
    """Helper to create a zip in memory from a folder."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in __import__("os").walk(folder):
            for file in files:
                full_path = Path(root) / file
                arcname = full_path.relative_to(folder)
                zf.write(full_path, arcname)
    return zip_buffer.getvalue()


def test_export_endpoint_creates_zip(tmp_path, monkeypatch):
    # Create a temporary source folder with sample files
    src_folder = tmp_path / "source"
    create_sample_files(src_folder)

    # Mock generate_evidence_zip to return in-memory zip content
    def mock_generate_zip(folder: Path) -> Path:
        # Return a temporary zip file with the folder contents
        temp_zip = tmp_path / "export.zip"
        temp_zip.write_bytes(create_zip_bytes(folder))
        return temp_zip

    # Patch at router module level (where it's imported)
    with patch("src.router.generate_evidence_zip", side_effect=mock_generate_zip):
        client = TestClient(app)

        # Call endpoint with folder query param (URL-encoded)
        url = f"/api/evidence/export?folder={quote(str(src_folder))}"
        resp = client.get(url)

        assert resp.status_code == 200
        # content-type may include charset or be one of several zip types
        assert "zip" in resp.headers.get("content-type", "")

        # Verify returned content is a zip and contains our files (allowing
        # for the exporter to include a parent folder name in archive entries)
        z = zipfile.ZipFile(io.BytesIO(resp.content))
        names = z.namelist()

        assert any(Path(n).name == "a.txt" for n in names), f"a.txt not in {names}"
        assert any(Path(n).as_posix().endswith("sub/b.txt") for n in names), (
            f"sub/b.txt not in {names}"
        )
