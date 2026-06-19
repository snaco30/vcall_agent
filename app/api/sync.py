from fastapi import APIRouter, Depends
import glob
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone

from app.api.auth import get_current_user

router = APIRouter(prefix="/api/sync", tags=["Sync"])

META_PATH = os.getenv("MDB_META_PATH", "/data/mdb_sync.meta")
MDB_PATH = os.getenv("MDB_PATH", "/data/vanpro97_call.mdb")
MOUNT_DIR = os.getenv("MDB_MOUNT_DIR", "/mnt/vcallmanager1")
STALE_MINUTES = int(os.getenv("MDB_SYNC_STALE_MINUTES", "10"))

MDB_CANDIDATES = (
    "VANPRO97_call.mdb",
    "vanpro97_call.mdb",
    "VANPRO97_CALL.MDB",
)


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


def _is_mounted(path: str) -> bool:
    target = os.path.normpath(path)
    try:
        with open("/proc/mounts", encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and os.path.normpath(parts[1]) == target:
                    return True
    except OSError:
        pass
    return False


def _resolve_src_mdb() -> str | None:
    for name in MDB_CANDIDATES:
        path = os.path.join(MOUNT_DIR, name)
        if os.path.isfile(path):
            return path
    matches = glob.glob(os.path.join(MOUNT_DIR, "[Vv][Aa][Nn][Pp][Rr][Oo]97_call.mdb"))
    return matches[0] if matches else None


def _verify_mdb(path: str) -> bool:
    try:
        result = subprocess.run(
            ["mdb-tables", path],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return True


def _write_meta(synced_at: str, source: str) -> None:
    meta_dir = os.path.dirname(META_PATH)
    if meta_dir:
        os.makedirs(meta_dir, exist_ok=True)
    tmp = f"{META_PATH}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"synced_at": synced_at, "source": source}, f, ensure_ascii=False)
        f.write("\n")
    os.chmod(tmp, 0o640)
    os.replace(tmp, META_PATH)


def _ensure_local_copy_meta() -> None:
    if not os.path.isfile(MDB_PATH) or os.path.isfile(META_PATH):
        return
    synced_at = _mdb_mtime_iso()
    if synced_at:
        _write_meta(synced_at, "local_copy")


LOCAL_FALLBACK_MSG = "원본 서버 연결 불가 — 최종 복사본 사용 중"


def _sync_failure_response(message: str) -> dict:
    _ensure_local_copy_meta()
    payload = _build_status_payload()
    if payload["using_local_fallback"]:
        message = LOCAL_FALLBACK_MSG
    else:
        message = f"{message} — 기존 복사본 유지"
    return {"ok": False, "message": message, **payload}


def _build_status_payload() -> dict:
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

    mount_available = _is_mounted(MOUNT_DIR)
    src_available = bool(_resolve_src_mdb()) if mount_available else False
    using_local_fallback = mdb_exists and not mount_available

    return {
        "synced_at": synced_at,
        "source": source,
        "has_sync_history": has_sync_history,
        "is_stale": is_stale if has_sync_history else True,
        "mdb_available": mdb_exists,
        "stale_threshold_minutes": STALE_MINUTES,
        "mount_available": mount_available,
        "src_available": src_available,
        "using_local_fallback": using_local_fallback,
    }


def run_mdb_sync() -> dict:
    if not _is_mounted(MOUNT_DIR):
        return _sync_failure_response(f"SMB 마운트 없음 ({MOUNT_DIR})")

    src = _resolve_src_mdb()
    if not src:
        try:
            listing = sorted(os.listdir(MOUNT_DIR))[:8]
        except OSError:
            listing = []
        hint = f" ({MOUNT_DIR})"
        if listing:
            hint += f" — 폴더 내용: {', '.join(listing)}"
        else:
            hint += " — 폴더가 비어 있음 (호스트 마운트 경로 확인)"
        return _sync_failure_response(f"마운트 폴더에 MDB 파일 없음{hint}")

    dst_dir = os.path.dirname(MDB_PATH)
    if dst_dir:
        os.makedirs(dst_dir, exist_ok=True)

    tmp = f"{MDB_PATH}.tmp"
    try:
        shutil.copy2(src, tmp)
    except OSError as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        return _sync_failure_response(f"복사 실패 ({e})")

    if not _verify_mdb(tmp):
        os.remove(tmp)
        return _sync_failure_response("MDB 무결성 검증 실패")

    os.chmod(tmp, 0o640)
    os.replace(tmp, MDB_PATH)

    synced_at = datetime.now().astimezone().isoformat(timespec="seconds")
    _write_meta(synced_at, src)

    return {
        "ok": True,
        "message": "동기화 완료",
        "synced_at": synced_at,
        "source": src,
        **_build_status_payload(),
    }


@router.get("/status")
def get_sync_status(current_user: str = Depends(get_current_user)):
    return _build_status_payload()


@router.post("/trigger")
def trigger_sync(current_user: str = Depends(get_current_user)):
    return run_mdb_sync()
