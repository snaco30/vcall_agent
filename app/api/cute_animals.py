from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi import APIRouter, Depends
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from app.api.auth import get_current_user

router = APIRouter(prefix="/api/cute-animal", tags=["CuteAnimal"])

CACHE_TTL_SECONDS = 3600
BATCH_SIZE = 20
_USER_AGENT = "vcall-agent/1.0"
_DOG_CEO_API = "https://dog.ceo/api/breeds/image/random"
_DOGAPI_SEARCH = "https://api.thedogapi.com/v1/images/search?limit={limit}&size=full&order=RANDOM"

_cache: dict = {
    "items": [],
    "fetched_at": 0.0,
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
            "image_url": url,
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


def _collect_images(target: int = BATCH_SIZE) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()

    def add(entry: dict) -> None:
        url = entry.get("image_url")
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
                        "image_url": url,
                        "width": 0,
                        "height": 0,
                        "animal": "dog",
                        "source": "dog.ceo",
                    })

    items.sort(key=lambda row: int(row.get("width") or 0), reverse=True)
    return items[:target]


def _cache_valid(now: float) -> bool:
    return bool(_cache.get("items")) and (now - float(_cache.get("fetched_at") or 0)) < CACHE_TTL_SECONDS


def _build_payload(ok: bool, message: str = "") -> dict:
    fetched_at = _cache.get("fetched_at") or 0
    expires_at = None
    items = _cache.get("items") or []
    if ok and fetched_at:
        expires_at = datetime.fromtimestamp(
            fetched_at + CACHE_TTL_SECONDS, tz=timezone.utc
        ).astimezone().isoformat(timespec="seconds")
    return {
        "ok": ok,
        "items": items if ok else [],
        "count": len(items) if ok else 0,
        "animal": "dog" if ok else None,
        "message": message or ("이미지 없음" if not ok else ""),
        "cached_until": expires_at,
        "refresh_seconds": CACHE_TTL_SECONDS,
        "slide_seconds": 8,
    }


@router.get("")
def get_cute_animal(current_user: str = Depends(get_current_user)):
    now = time.time()
    if _cache_valid(now):
        return _build_payload(True)

    items = _collect_images(BATCH_SIZE)
    if not items:
        return _build_payload(False, "이미지 없음")

    _cache.update({
        "items": items,
        "fetched_at": now,
    })
    return _build_payload(True)
