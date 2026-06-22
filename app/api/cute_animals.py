from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from io import BytesIO
from pathlib import Path
import json
import os
import re
import shutil
import time
import urllib.error
import urllib.request
import uuid

from PIL import Image

from app.api.auth import get_current_user, get_current_user_for_media

router = APIRouter(prefix="/api/cute-animal", tags=["CuteAnimal"])

CACHE_TTL_SECONDS = 3600
BATCH_SIZE = 20
_USER_AGENT = "vcall-agent/1.0"
_DOG_CEO_API = "https://dog.ceo/api/breeds/image/random"
_DOGAPI_SEARCH = "https://api.thedogapi.com/v1/images/search?limit={limit}&size=full&order=RANDOM"
_CACHE_DIR = Path(os.environ.get("CUTE_ANIMAL_CACHE_DIR", "/data/cute_animal_cache"))
_DISPLAY_MAX_PX = 720
_FULL_MAX_PX = 1280
_JPEG_QUALITY_VIEW = 82
_JPEG_QUALITY_FULL = 88
_BATCH_ID_RE = re.compile(r"^[a-f0-9]{12}$")

_cache: dict = {
    "batch_id": "",
    "items": [],
    "fetched_at": 0.0,
    "prepare_seconds": 0.0,
}


def _fetch_json(url: str, timeout: int = 10) -> object | None:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def _fetch_dogapi_batch(limit: int = 10) -> list[dict]:
    data = _fetch_json(_DOGAPI_SEARCH.format(limit=limit))
    if not isinstance(data, list):
        return []

    items: list[dict] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        url = row.get("url")
        if not isinstance(url, str) or not url.startswith("http"):
            continue
        width = row.get("width") or 0
        height = row.get("height") or 0
        items.append({
            "source_url": url,
            "width": int(width) if isinstance(width, (int, float)) else 0,
            "height": int(height) if isinstance(height, (int, float)) else 0,
            "animal": "dog",
            "source": "thedogapi",
        })
    return items


def _fetch_one_dog_ceo_url() -> str | None:
    data = _fetch_json(_DOG_CEO_API)
    if isinstance(data, dict) and data.get("status") == "success":
        url = data.get("message")
        if isinstance(url, str) and url.startswith("http"):
            return url
    return None


def _collect_source_urls(target: int = BATCH_SIZE) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()

    def add(entry: dict) -> None:
        url = entry.get("source_url")
        if not isinstance(url, str) or url in seen or len(items) >= target:
            return
        seen.add(url)
        items.append(entry)

    for batch_limit in (10, 10):
        if len(items) >= target:
            break
        for row in _fetch_dogapi_batch(batch_limit):
            add(row)

    workers = min(8, target)
    attempts = max(target - len(items), 0) + 8
    if attempts > 0 and len(items) < target:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_fetch_one_dog_ceo_url) for _ in range(attempts)]
            for future in as_completed(futures):
                if len(items) >= target:
                    break
                try:
                    url = future.result()
                except Exception:
                    continue
                if url:
                    add({
                        "source_url": url,
                        "width": 0,
                        "height": 0,
                        "animal": "dog",
                        "source": "dog.ceo",
                    })

    items.sort(key=lambda row: int(row.get("width") or 0), reverse=True)
    return items[:target]


def _download_bytes(url: str) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def _encode_jpeg(img: Image.Image, max_side: int, quality: int) -> bytes:
    work = img.copy()
    if work.mode not in ("RGB", "L"):
        work = work.convert("RGB")
    work.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    buf = BytesIO()
    work.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def _process_source(idx: int, entry: dict, batch_dir: Path) -> dict | None:
    raw = _download_bytes(entry["source_url"])
    if not raw:
        return None

    try:
        with Image.open(BytesIO(raw)) as img:
            view_bytes = _encode_jpeg(img, _DISPLAY_MAX_PX, _JPEG_QUALITY_VIEW)
            full_bytes = _encode_jpeg(img, _FULL_MAX_PX, _JPEG_QUALITY_FULL)
    except OSError:
        return None

    view_path = batch_dir / f"{idx:03d}_view.jpg"
    full_path = batch_dir / f"{idx:03d}_full.jpg"
    view_path.write_bytes(view_bytes)
    full_path.write_bytes(full_bytes)

    return {
        "index": idx,
        "image_url": f"/api/cute-animal/file/{batch_dir.name}/{idx}/view",
        "full_url": f"/api/cute-animal/file/{batch_dir.name}/{idx}/full",
        "source_url": entry["source_url"],
        "animal": entry.get("animal", "dog"),
        "source": entry.get("source", ""),
        "bytes_view": len(view_bytes),
        "bytes_full": len(full_bytes),
        "orig_bytes": len(raw),
    }


def _cleanup_old_batches(keep_batch_id: str) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for path in _CACHE_DIR.iterdir():
        if not path.is_dir():
            continue
        if path.name == keep_batch_id:
            continue
        shutil.rmtree(path, ignore_errors=True)


def _batch_files_exist(batch_id: str, count: int) -> bool:
    batch_dir = _CACHE_DIR / batch_id
    if not batch_dir.is_dir():
        return False
    for idx in range(count):
        if not (batch_dir / f"{idx:03d}_view.jpg").is_file():
            return False
        if not (batch_dir / f"{idx:03d}_full.jpg").is_file():
            return False
    return True


def _prepare_batch(sources: list[dict]) -> tuple[str, list[dict], float]:
    batch_id = uuid.uuid4().hex[:12]
    batch_dir = _CACHE_DIR / batch_id
    batch_dir.mkdir(parents=True, exist_ok=False)
    started = time.time()

    prepared: list[dict] = []
    workers = min(6, max(len(sources), 1))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_process_source, idx, entry, batch_dir): idx
            for idx, entry in enumerate(sources)
        }
        results: dict[int, dict] = {}
        for future in as_completed(futures):
            try:
                row = future.result()
            except Exception:
                continue
            if row is not None:
                results[row["index"]] = row

    for idx in sorted(results):
        prepared.append(results[idx])

    if not prepared:
        shutil.rmtree(batch_dir, ignore_errors=True)
        return "", [], time.time() - started

    _cleanup_old_batches(batch_id)
    return batch_id, prepared, time.time() - started


def _cache_valid(now: float) -> bool:
    if not _cache.get("items") or not _cache.get("batch_id"):
        return False
    if (now - float(_cache.get("fetched_at") or 0)) >= CACHE_TTL_SECONDS:
        return False
    return _batch_files_exist(_cache["batch_id"], len(_cache["items"]))


def _build_payload(ok: bool, message: str = "") -> dict:
    fetched_at = _cache.get("fetched_at") or 0
    expires_at = None
    items = _cache.get("items") or []
    if ok and fetched_at:
        expires_at = datetime.fromtimestamp(
            fetched_at + CACHE_TTL_SECONDS, tz=timezone.utc
        ).astimezone().isoformat(timespec="seconds")

    avg_orig = 0
    avg_view = 0
    if items:
        avg_orig = int(sum(int(i.get("orig_bytes") or 0) for i in items) / len(items))
        avg_view = int(sum(int(i.get("bytes_view") or 0) for i in items) / len(items))

    return {
        "ok": ok,
        "batch_id": _cache.get("batch_id") if ok else None,
        "items": items if ok else [],
        "count": len(items) if ok else 0,
        "animal": "dog" if ok else None,
        "message": message or ("이미지 없음" if not ok else ""),
        "cached_until": expires_at,
        "refresh_seconds": CACHE_TTL_SECONDS,
        "slide_seconds": 8,
        "prepare_seconds": round(float(_cache.get("prepare_seconds") or 0), 2),
        "serving": "local_resized" if ok else None,
        "display_max_px": _DISPLAY_MAX_PX,
        "full_max_px": _FULL_MAX_PX,
        "slow_reason": (
            "이전에는 외부 CDN 원본(평균 "
            f"{avg_orig // 1024}KB)을 브라우저가 직접 받아 느렸습니다. "
            f"서버에서 {_DISPLAY_MAX_PX}px로 줄여 평균 {avg_view // 1024}KB로 제공합니다."
            if ok and avg_orig > 0
            else None
        ),
    }


def _refresh_cache() -> bool:
    sources = _collect_source_urls(BATCH_SIZE)
    if not sources:
        return False

    batch_id, items, prepare_seconds = _prepare_batch(sources)
    if not items:
        return False

    _cache.update({
        "batch_id": batch_id,
        "items": items,
        "fetched_at": time.time(),
        "prepare_seconds": prepare_seconds,
    })
    return True


@router.get("")
def get_cute_animal(current_user: str = Depends(get_current_user)):
    now = time.time()
    if not _cache_valid(now):
        if not _refresh_cache():
            return _build_payload(False, "이미지 없음")
    return _build_payload(True)


@router.get("/file/{batch_id}/{index}/{variant}")
def get_cute_animal_file(
    batch_id: str,
    index: int,
    variant: str,
    current_user: str = Depends(get_current_user_for_media),
):
    if not _BATCH_ID_RE.match(batch_id):
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다.")
    if variant not in ("view", "full"):
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다.")
    if index < 0 or index >= BATCH_SIZE:
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다.")

    path = _CACHE_DIR / batch_id / f"{index:03d}_{variant}.jpg"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다.")

    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )
