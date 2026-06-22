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

_cache: dict = {
    "items": [],
    "fetched_at": 0.0,
}


def _fetch_json(url: str, timeout: int = 8) -> object | None:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def _collect_images(target: int = BATCH_SIZE) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()

    def add(url: object, animal: str) -> None:
        if not isinstance(url, str) or not url.startswith("http") or url in seen:
            return
        if len(items) >= target:
            return
        seen.add(url)
        items.append({"image_url": url, "animal": animal})

    for limit in (10, 10):
        if len(items) >= target:
            break
        cat_data = _fetch_json(
            f"https://api.thecatapi.com/v1/images/search?limit={min(limit, target - len(items))}"
        )
        if isinstance(cat_data, list):
            for row in cat_data:
                if isinstance(row, dict):
                    add(row.get("url"), "cat")

    attempts = 0
    while len(items) < target and attempts < target * 4:
        attempts += 1
        if attempts % 3 == 1:
            dog_data = _fetch_json("https://dog.ceo/api/breeds/image/random")
            if isinstance(dog_data, dict) and dog_data.get("status") == "success":
                add(dog_data.get("message"), "dog")
        elif attempts % 3 == 2:
            fox_data = _fetch_json("https://randomfox.ca/floof/")
            if isinstance(fox_data, dict):
                add(fox_data.get("image"), "fox")
        else:
            cat_data = _fetch_json("https://api.thecatapi.com/v1/images/search?limit=1")
            if isinstance(cat_data, list) and cat_data and isinstance(cat_data[0], dict):
                add(cat_data[0].get("url"), "cat")

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
