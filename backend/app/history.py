from datetime import datetime, timezone

from bson import ObjectId
from pymongo import MongoClient

from app.config import MONGO_URL

_client = None


def _col():
    global _client
    if not MONGO_URL:
        return None
    if _client is None:
        _client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
    return _client["agentcrew"]["runs"]


def save_run(doc: dict):
    """Best effort: a history failure must never break a finished run."""
    try:
        col = _col()
        if col is None:
            return None
        return str(col.insert_one({**doc, "created_at": datetime.now(timezone.utc)}).inserted_id)
    except Exception:
        return None


def list_runs(limit: int = 20):
    col = _col()
    if col is None:
        return []
    cursor = (
        col.find({}, {"goal": 1, "approved": 1, "drafts": 1, "created_at": 1})
        .sort("created_at", -1)
        .limit(limit)
    )
    return [
        {
            "id": str(d["_id"]),
            "goal": d["goal"],
            "approved": d.get("approved"),
            "drafts": d.get("drafts"),
            "created_at": d["created_at"].isoformat(),
        }
        for d in cursor
    ]


def get_run(run_id: str):
    col = _col()
    if col is None:
        return None
    try:
        d = col.find_one({"_id": ObjectId(run_id)})
    except Exception:
        return None
    if not d:
        return None
    d["id"] = str(d.pop("_id"))
    d["created_at"] = d["created_at"].isoformat()
    return d