from pathlib import Path
from src.utils.court_bundle import build_court_bundle


def test_build_court_bundle():
    # Use the same small folder used earlier for export tests
    test_folder = Path.home() / "Mitchopolis" / "parenting_evidence" / "text_logs"
    assert test_folder.exists(), f"Missing test folder: {test_folder}"

    zip_path = build_court_bundle("test_case", test_folder)
    assert zip_path.exists(), "Bundle ZIP was not created"
