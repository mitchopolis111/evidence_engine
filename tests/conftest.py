import sys
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Unit/API tests should not depend on a developer's local .env MongoDB setting.
os.environ["MONGO_URI"] = ""
