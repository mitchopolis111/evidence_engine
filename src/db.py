import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")

client = None
db = None

if MONGO_URI:
    client = MongoClient(MONGO_URI)
    db = client["evidence_pipeline"]


def get_db():
    return db


def get_collection(name: str):
    if db is None:
        return None
    return db[name]
