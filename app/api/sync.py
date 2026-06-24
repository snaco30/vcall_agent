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
MOUNT_DIR_CANDIDATES = tuple(
    dict.fromkeys(
        path
        for path in (
            MOUNT_DIR,
            "/mnt/vcallmanager1",
            "/data/mnt/vcallmanager1",
        )
        if path
    )
)
STALE_MINUTES = int(os.getenv("MDB_SYNC_STALE_MINUTES", "60"))

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


def _is_accessible(path: str) -> bool:
    try:
        os.listdir(path)
        return True
    except OSError:
        return False


def _mount_is_stale() -> bool:
    active = _active_mount_dir()
    if not active:
        return False
    info = _inspect_mount(active)
    return info["mount_stale"]


def _resolve_src_mdb(mount_dir: str | None = None) -> str | None:
    search_dirs = (mount_dir,) if mount_dir else MOUNT_DIR_CANDIDATES
    for base in search_dirs:
        for name in MDB_CANDIDATES:
            path = os.path.join(base, name)
            if os.path.isfile(path):
                return path
        matches = glob.glob(os.path.join(base, "[Vv][Aa][Nn][Pp][Rr][Oo]97_call.mdb"))
        if matches:
            return matches[0]
    return None


def _active_mount_dir() -> str | None:
    for mount_dir in MOUNT_DIR_CANDIDATES:
        if not _is_mounted(mount_dir) and not _is_accessible(mount_dir):
            continue
        if _resolve_src_mdb(mount_dir):
            return mount_dir
    for mount_dir in MOUNT_DIR_CANDIDATES:
        if _is_mounted(mount_dir) or _is_accessible(mount_dir):
            return mount_dir
    return MOUNT_DIR_CANDIDATES[0] if MOUNT_DIR_CANDIDATES else MOUNT_DIR


def _inspect_mount(mount_dir: str) -> dict:
    mount_listed = _is_mounted(mount_dir)
    mount_accessible = mount_listed and _is_accessible(mount_dir)
    if not mount_listed and _is_accessible(mount_dir):
        mount_accessible = True
    src_available = bool(_resolve_src_mdb(mount_dir)) if mount_accessible else False
    mount_stale = mount_listed and (not mount_accessible or not src_available)
    mount_available = mount_accessible and src_available
    return {
        "mount_dir": mount_dir,
        "mount_listed": mount_listed,
        "mount_accessible": mount_accessible,
        "src_available": src_available,
        "mount_stale": mount_stale,
        "mount_available": mount_available,
    }


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
    if payload.get("mount_stale"):
        if not message.endswith("유지"):
            message = f"{message} — 기존 복사본 유지"
    elif payload["using_local_fallback"]:
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

    mount_dir = _active_mount_dir() or MOUNT_DIR
    mount_info = _inspect_mount(mount_dir)
    mount_available = mount_info["mount_available"]
    mount_stale = mount_info["mount_stale"]
    src_available = mount_info["src_available"]
    using_local_fallback = mdb_exists and not mount_available

    return {
        "synced_at": synced_at,
        "source": source,
        "has_sync_history": has_sync_history,
        "is_stale": is_stale if has_sync_history else True,
        "mdb_available": mdb_exists,
        "stale_threshold_minutes": STALE_MINUTES,
        "mount_dir": mount_dir,
        "mount_available": mount_available,
        "mount_stale": mount_stale,
        "src_available": src_available,
        "using_local_fallback": using_local_fallback,
    }


def run_mdb_sync() -> dict:
    mount_dir = _active_mount_dir() or MOUNT_DIR
    mount_info = _inspect_mount(mount_dir)

    if not mount_info["mount_listed"] and not mount_info["mount_accessible"]:
        return _sync_failure_response(f"SMB 마운트 없음 ({mount_dir})")

    if mount_info["mount_listed"] and not mount_info["mount_accessible"]:
        return _sync_failure_response(
            f"SMB 마운트 끊김 ({mount_dir}) — 호스트에서 sync-mdb.sh 가 자동 복구 시도"
        )

    src = _resolve_src_mdb(mount_dir)
    if not src:
        hint = (
            "Docker가 SMB 하위 마운트를 못 볼 수 있습니다. "
            "호스트에서 ./deploy.sh 재실행 또는 scripts/mount-mdb-share.sh --check"
        )
        return _sync_failure_response(
            f"SMB 마운트 비정상 ({mount_dir}) — MDB 파일 없음. {hint}"
        )

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
