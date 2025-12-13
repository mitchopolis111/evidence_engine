from pathlib import Path
from src.utils.zip_exporter import generate_evidence_zip


def test_zip_creation():
    # Use a small known folder for test (e.g., text_logs)
    test_folder = Path.home() / "Mitchopolis" / "parenting_evidence" / "text_logs"

    assert test_folder.exists(), f"Test folder missing: {test_folder}"

    zip_path = generate_evidence_zip(test_folder)

    assert zip_path.exists(), "ZIP file was not created"
    print("ZIP created at:", zip_path)


if __name__ == "__main__":
    # Allow running this file directly for quick manual verification.
    test_zip_creation()

    # Manual run reminder:
    # cd ~/Mitchopolis/evidence_engine
    # source venv/bin/activate
    # python test_zip_exporter.py
