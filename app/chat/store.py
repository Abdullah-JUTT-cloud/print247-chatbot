"""Session slot storage in Mongo — fail-soft by design.

load/save raise nothing to the caller: brain.py wraps them anyway.
If Mongo is down, a chat still answers this message; it just does
not remember the previous ones. That is the right trade-off for a
sales chat: a database outage must not become a visitor outage.
"""
import os


class SlotStore:
    def __init__(self):
        from pymongo import MongoClient

        self._client = MongoClient(
            os.environ.get("MONGO_URI", "mongodb://localhost:27017/print247_chatbot"),
            serverSelectionTimeoutMS=2000)
        self._col = self._client.get_default_database()["sessions"]

    def load(self, session_id: str) -> dict:
        doc = self._col.find_one({"_id": session_id})
        return (doc or {}).get("slots", {})

    def save(self, session_id: str, slots: dict) -> None:
        self._col.update_one(
            {"_id": session_id}, {"$set": {"slots": slots}}, upsert=True)


def get_store():
    try:
        return SlotStore()
    except Exception:
        return None
