import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = (
    os.getenv("MONGO_URI")
    or os.getenv("DATABASE_URL")
    or "mongodb://127.0.0.1:27017"
)
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "evidence_pipeline")
client = MongoClient(
    MONGO_URI,
    tz_aware=True,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
)
db = client[MONGO_DB_NAME]
