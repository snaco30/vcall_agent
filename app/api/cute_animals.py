from fastapi import APIRouter, Depends
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from app.api.auth import get_current_user

router = APIRouter(prefix="/api/cute-animal", tags=["CuteAnimal"])

CACHE_TTL_SECONDS = 3600
_USER_AGENT = "vcall-agent/1.0"

_cache: dict = {
    "image_url": None,
    "animal": None,
    "source": None,
    "fetched_at": 0.0,
}


def _fetch_json(url: str, timeout: int = 8) -> object | None:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def _pick_image_url() -> tuple[str | None, str | None]:
    cat_data = _fetch_json("https://api.thecatapi.com/v1/images/search?limit=1")
    if isinstance(cat_data, list) and cat_data:
        url = cat_data[0].get("url") if isinstance(cat_data[0], dict) else None
        if url:
            return url, "cat"

    dog_data = _fetch_json("https://dog.ceo/api/breeds/image/random")
    if isinstance(dog_data, dict) and dog_data.get("status") == "success":
        url = dog_data.get("message")
        if isinstance(url, str) and url.startswith("http"):
            return url, "dog"

    fox_data = _fetch_json("https://randomfox.ca/floof/")
    if isinstance(fox_data, dict):
        url = fox_data.get("image")
        if isinstance(url, str) and url.startswith("http"):
            return url, "fox"

    return None, None


def _cache_valid(now: float) -> bool:
    return bool(_cache.get("image_url")) and (now - float(_cache.get("fetched_at") or 0)) < CACHE_TTL_SECONDS


def _build_payload(ok: bool, message: str = "") -> dict:
    now = time.time()
    fetched_at = _cache.get("fetched_at") or 0
    expires_at = None
    if ok and fetched_at:
        expires_at = datetime.fromtimestamp(fetched_at + CACHE_TTL_SECONDS, tz=timezone.utc).astimezone().isoformat(timespec="seconds")
    return {
        "ok": ok,
        "image_url": _cache.get("image_url") if ok else None,
        "animal": _cache.get("animal") if ok else None,
        "source": _cache.get("source") if ok else None,
        "message": message or ("이미지 없음" if not ok else ""),
        "cached_until": expires_at,
        "refresh_seconds": CACHE_TTL_SECONDS,
    }


@router.get("")
def get_cute_animal(current_user: str = Depends(get_current_user)):
    now = time.time()
    if _cache_valid(now):
        return _build_payload(True)

    image_url, animal = _pick_image_url()
    if not image_url:
        return _build_payload(False, "이미지 없음")

    _cache.update({
        "image_url": image_url,
        "animal": animal,
        "source": "web",
        "fetched_at": now,
    })
    return _build_payload(True)
