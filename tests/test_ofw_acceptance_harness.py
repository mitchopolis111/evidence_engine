"""Privacy-safe checks of failures in the opt-in acceptance harness."""

import subprocess
import sys
from pathlib import Path

import pytest


REPOSITORY = Path(__file__).resolve().parents[1]


def _pytest(*args):
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-c", str(REPOSITORY / "pytest.ini"), *args],
        cwd=REPOSITORY,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


@pytest.mark.parametrize("day", ["16", "30"])
def test_explicit_empty_private_export_path_fails_instead_of_skipping(day):
    result = _pytest(f"tests/test_ofw_oct{day}_export.py", f"--ofw-oct{day}-export=")
    assert result.returncode == 1
    assert f"explicit --ofw-oct{day}-export path" in result.stdout
    # Cross-report tests can skip when the other private report is absent.


@pytest.mark.parametrize("failure", ["assertion", "exception", "fixture"])
def test_private_checks_hide_evidence_in_failure_output(tmp_path, failure):
    sentinel = "SYNTHETIC_PRIVATE_EVIDENCE_SENTINEL"
    if failure == "fixture":
        source = '''
import pytest
from tests.ofw_private_checks import private_export_checks

@pytest.fixture
def private_fixture():
    with private_export_checks():
        raise ValueError("SYNTHETIC_PRIVATE_EVIDENCE_SENTINEL")

def test_private_failure(private_fixture):
    pass
'''
    else:
        operation = (
            'assert payload == {"filename": "different"}'
            if failure == "assertion" else 'raise ValueError(payload["filename"])'
        )
        source = f'''
from tests.ofw_private_checks import private_export_checks

def test_private_failure():
    payload = {{"filename": "{sentinel}"}}
    with private_export_checks():
        {operation}
'''
    test_file = tmp_path / "test_private_failure.py"
    test_file.write_text(source)
    result = _pytest(str(test_file), "--showlocals")
    assert result.returncode == 1
    assert "Private OFW validation failed" in result.stdout
    assert sentinel not in result.stdout + result.stderr
