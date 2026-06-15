import os

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        return False

try:
    from pymongo import MongoClient
except ImportError:
    MongoClient = None

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")

client = None
db = None


def _mongo_server_selection_timeout_ms() -> int:
    try:
        return int(os.getenv("MONGO_SERVER_SELECTION_TIMEOUT_MS", "2000"))
    except ValueError:
        return 2000


if MONGO_URI and MongoClient is not None:
    client = MongoClient(
        MONGO_URI,
        serverSelectionTimeoutMS=_mongo_server_selection_timeout_ms(),
    )
    db = client["evidence_pipeline"]


def get_db():
    return db


def get_collection(name: str):
    if db is None:
        return None
    return db[name]
