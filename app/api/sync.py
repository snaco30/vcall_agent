from fastapi import APIRouter, Depends
import json
import os
from datetime import datetime, timezone

from app.api.auth import get_current_user

router = APIRouter(prefix="/api/sync", tags=["Sync"])

META_PATH = os.getenv("MDB_META_PATH", "/data/mdb_sync.meta")
MDB_PATH = os.getenv("MDB_PATH", "/data/vanpro97_call.mdb")
STALE_MINUTES = int(os.getenv("MDB_SYNC_STALE_MINUTES", "10"))


def _mdb_mtime_iso() -> str | None:
    try:
        mtime = os.path.getmtime(MDB_PATH)
    except OSError:
        return None
    return datetime.fromtimestamp(mtime).astimezone().isoformat(timespec="seconds")


def _parse_synced_at(value: str) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


@router.get("/status")
def get_sync_status(current_user: str = Depends(get_current_user)):
    synced_at = None
    source = None
    has_sync_history = False

    if os.path.isfile(META_PATH):
        try:
            with open(META_PATH, encoding="utf-8") as f:
                meta = json.load(f)
            synced_at = meta.get("synced_at")
            source = meta.get("source")
            if synced_at and source != "local_copy":
                has_sync_history = True
        except (json.JSONDecodeError, OSError):
            pass

    mdb_exists = os.path.isfile(MDB_PATH)
    if not synced_at and mdb_exists:
        synced_at = _mdb_mtime_iso()
        source = source or "local_copy"

    parsed = _parse_synced_at(synced_at) if synced_at else None
    is_stale = True
    if parsed:
        age = datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)
        is_stale = age.total_seconds() > STALE_MINUTES * 60

    return {
        "synced_at": synced_at,
        "source": source,
        "has_sync_history": has_sync_history,
        "is_stale": is_stale if has_sync_history else True,
        "mdb_available": mdb_exists,
        "stale_threshold_minutes": STALE_MINUTES,
    }
