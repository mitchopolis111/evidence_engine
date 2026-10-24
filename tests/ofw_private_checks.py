"""Keep private fixture values out of pytest errors, including --showlocals."""

from contextlib import contextmanager
from pathlib import Path

import pytest


@contextmanager
def private_export_checks():
    try:
        yield
    except Exception as exc:
        # Keep the failing code location, never the exception text or locals.
        frame = exc.__traceback__
        while frame.tb_next is not None:
            frame = frame.tb_next
        location = f"{Path(frame.tb_frame.f_code.co_filename).name}:{frame.tb_lineno}"
        message = (
            f"Private OFW validation failed ({type(exc).__name__} at {location}); "
            "evidence contents withheld. Inspect the isolated copy locally."
        )
        raise pytest.fail.Exception(message, pytrace=False) from None
