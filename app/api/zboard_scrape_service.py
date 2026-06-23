"""ZeroBoard 4.x 게시판 스크랩 서비스 (FastAPI 비의존)."""

from __future__ import annotations

import io
import mimetypes
import re
import time
import uuid
from dataclasses import dataclass
from html import unescape
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; VCallBoardScraper/1.0)"
DEFAULT_DELAY_SEC = 0.35
MAX_POSTS_PER_RUN = 1000
SOURCE_PREFIX = "zboard"

KICCPOS_BOARD_URL = "http://jaypos.com/zb41pl8/bbs/zboard.php?id=KICCPOS"


class ZboardScrapeError(ValueError):
    """스크랩 파싱·가져오기 오류."""


def _sanitize_html(raw_html: str) -> str:
    from app.api.board.common import sanitize_html

    return sanitize_html(raw_html)


def _board_db():
    from app.api import board_db

    return board_db


@dataclass
class ZboardSource:
    base_url: str
    board_id: str
    list_url: str


@dataclass
class ZboardListItem:
    no: int
    title: str
    is_pinned: bool


@dataclass
class ZboardPost:
    no: int
    title: str
    body_html: str
    author: str
    posted_at: str | None
    is_pinned: bool
    view_count: int


def parse_zboard_source_url(url: str) -> ZboardSource:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https"):
        raise ZboardScrapeError("http 또는 https URL만 지원합니다.")
    query = parse_qs(parsed.query)
    board_id = (query.get("id") or [""])[0].strip()
    if not board_id:
        raise ZboardScrapeError("ZeroBoard URL에 id= 파라미터가 필요합니다.")
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path or "/zb41pl8/bbs/zboard.php"
    if not path.endswith("zboard.php"):
        raise ZboardScrapeError("ZeroBoard 목록 URL(zboard.php?id=...)을 입력해 주세요.")
    list_url = f"{base_url}{path}?id={board_id}"
    return ZboardSource(base_url=base_url, board_id=board_id, list_url=list_url)


def _decode_html(content: bytes) -> str:
    for encoding in ("utf-8", "euc-kr", "cp949", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def fetch_html(_client: Any, url: str) -> str:
    request = Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    with urlopen(request, timeout=30) as response:
        return _decode_html(response.read())


def fetch_bytes(_client: Any, url: str) -> bytes:
    request = Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    with urlopen(request, timeout=30) as response:
        return response.read()


def _clean_title(raw: str) -> str:
    title = unescape(re.sub(r"\s+", " ", raw or "")).strip()
    title = re.sub(r"^[★☆▶▷■□●○\s]+", "", title)
    return title


def parse_list_page(html: str, source: ZboardSource) -> list[ZboardListItem]:
    soup = BeautifulSoup(html, "html.parser")
    items: dict[int, ZboardListItem] = {}
    board_token = f"id={source.board_id}"

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if board_token not in href or "no=" not in href:
            continue
        match = re.search(r"[?&]no=(\d+)", href)
        if not match:
            continue
        post_no = int(match.group(1))
        if post_no <= 0:
            continue

        title = _clean_title(anchor.get_text(" ", strip=True))
        if not title or title in {"목록보기", "글쓰기", "로그인"}:
            continue

        parent_html = str(anchor.parent) if anchor.parent else ""
        is_pinned = "<b>" in parent_html.lower() and "list_han" in parent_html.lower()
        prev = items.get(post_no)
        if prev and len(prev.title) >= len(title):
            continue
        items[post_no] = ZboardListItem(no=post_no, title=title, is_pinned=is_pinned)

    return sorted(items.values(), key=lambda item: item.no, reverse=True)


def parse_max_page(html: str, source: ZboardSource) -> int:
    soup = BeautifulSoup(html, "html.parser")
    max_page = 1
    board_token = f"id={source.board_id}"
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if board_token not in href:
            continue
        match = re.search(r"[?&]page=(\d+)", href)
        if match:
            max_page = max(max_page, int(match.group(1)))
    return max_page


def collect_list_items(client: Any, source: ZboardSource, max_pages: int | None = None) -> list[ZboardListItem]:
    first_html = fetch_html(client, source.list_url)
    total_pages = parse_max_page(first_html, source)
    if max_pages is not None:
        total_pages = min(total_pages, max_pages)

    merged: dict[int, ZboardListItem] = {}
    for page in range(1, total_pages + 1):
        page_url = f"{source.list_url}&page={page}" if page > 1 else source.list_url
        html = first_html if page == 1 else fetch_html(client, page_url)
        for item in parse_list_page(html, source):
            merged[item.no] = item
        if page < total_pages:
            time.sleep(DEFAULT_DELAY_SEC)

    result = sorted(merged.values(), key=lambda item: item.no, reverse=True)
    if len(result) > MAX_POSTS_PER_RUN:
        raise ZboardScrapeError(f"한 번에 최대 {MAX_POSTS_PER_RUN}건까지만 가져올 수 있습니다.")
    return result


def parse_view_page(html: str, source: ZboardSource, post_no: int, is_pinned: bool = False) -> ZboardPost:
    soup = BeautifulSoup(html, "html.parser")

    title_td = soup.find("td", class_="title_han")
    title = _clean_title(title_td.get_text(" ", strip=True) if title_td else "")

    body_td = soup.select_one("tr.list1 td[valign=top] td.list_han")
    if not body_td:
        body_td = soup.find("td", class_="list_han")
    body_html = ""
    if body_td:
        inner_parts: list[str] = []
        for child in body_td.children:
            if getattr(child, "name", None) == "table":
                continue
            inner_parts.append(str(child))
        body_html = _sanitize_html("".join(inner_parts).strip())

    author = ""
    author_el = soup.select_one("tr.list1 span font.list_han")
    if author_el:
        author = author_el.get_text(strip=True)

    posted_at = None
    date_match = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", html)
    if date_match:
        posted_at = date_match.group(1)

    view_count = 0
    view_match = re.search(r"view count\s*:\s*<b>(\d+)</b>", html, re.I)
    if view_match:
        view_count = int(view_match.group(1))

    if not title:
        raise ZboardScrapeError(f"글 제목을 찾을 수 없습니다. (no={post_no})")

    return ZboardPost(
        no=post_no,
        title=title,
        body_html=body_html or "<p></p>",
        author=author,
        posted_at=posted_at,
        is_pinned=is_pinned,
        view_count=view_count,
    )


def build_view_url(source: ZboardSource, post_no: int) -> str:
    return f"{source.base_url}/zb41pl8/bbs/view.php?id={source.board_id}&no={post_no}"


def source_ref(source: ZboardSource, post_no: int) -> str:
    return f"{SOURCE_PREFIX}:{source.board_id}:{post_no}"


def find_board_by_name(name: str) -> dict[str, Any] | None:
    db = _board_db()
    needle = (name or "").strip()
    if not needle:
        return None
    return db.fetch_one(
        "SELECT * FROM boards WHERE name = ? COLLATE NOCASE LIMIT 1",
        (needle,),
    ) or db.fetch_one(
        "SELECT * FROM boards WHERE name LIKE ? COLLATE NOCASE LIMIT 1",
        (f"%{needle}%",),
    )


def existing_source_refs(board_id: int, refs: list[str]) -> set[str]:
    db = _board_db()
    if not refs:
        return set()
    placeholders = ",".join("?" for _ in refs)
    rows = db.fetch_all(
        f"""
        SELECT source_ref FROM posts
        WHERE board_id = ? AND deleted_at IS NULL AND source_ref IN ({placeholders})
        """,
        (board_id, *refs),
    )
    return {str(row["source_ref"]) for row in rows if row.get("source_ref")}


def preview_scrape(source_url: str, max_pages: int | None = None) -> dict[str, Any]:
    source = parse_zboard_source_url(source_url)
    items = collect_list_items(None, source, max_pages=max_pages)
    return {
        "source_url": source_url,
        "board_id": source.board_id,
        "base_url": source.base_url,
        "total_posts": len(items),
        "pinned_count": sum(1 for item in items if item.is_pinned),
        "sample_titles": [item.title for item in items[:8]],
    }


def _save_inline_image(post_id: int, filename: str, content: bytes, mime_type: str, author: str) -> int:
    db = _board_db()
    post_dir = db.BOARD_FILES_ROOT / str(post_id)
    post_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{PathLike_suffix(filename)}"
    (post_dir / stored_name).write_bytes(content)
    return db.execute(
        """
        INSERT INTO post_files(post_id, kind, original_name, stored_name, mime_type, size_bytes, sort_order, created_by, created_at)
        VALUES (?, 'inline', ?, ?, ?, ?, 0, ?, ?)
        """,
        (post_id, filename, stored_name, mime_type, len(content), author, db.utc_now_iso()),
    )


def PathLike_suffix(filename: str) -> str:
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ".jpg"
    if suffix not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        return ".jpg"
    return suffix


def _mirror_images(
    client: Any,
    post_id: int,
    body_html: str,
    page_url: str,
    author: str,
) -> str:
    soup = BeautifulSoup(body_html or "", "html.parser")
    changed = False
    for img in soup.find_all("img"):
        src = (img.get("src") or "").strip()
        if not src or src.startswith("data:"):
            continue
        abs_url = urljoin(page_url, src)
        if abs_url.endswith("/t.gif") or "t.gif" in abs_url:
            img.decompose()
            changed = True
            continue
        try:
            content = fetch_bytes(client, abs_url)
            if len(content) < 32:
                continue
            filename = abs_url.rsplit("/", 1)[-1].split("?")[0] or "image.jpg"
            mime_type = mimetypes.guess_type(filename)[0] or "image/jpeg"
            file_id = _save_inline_image(post_id, filename, content, mime_type, author)
            img["src"] = f"/api/boards/media/{file_id}"
            changed = True
            time.sleep(DEFAULT_DELAY_SEC / 2)
        except Exception:
            continue
    return _sanitize_html(str(soup)) if changed else body_html


def import_scrape(
    target_board_id: int,
    source_url: str,
    author_username: str,
    *,
    max_pages: int | None = None,
    skip_existing: bool = True,
    mirror_images: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    db = _board_db()
    board = db.fetch_one("SELECT * FROM boards WHERE id = ?", (target_board_id,))
    if not board:
        raise ZboardScrapeError("대상 게시판을 찾을 수 없습니다.")

    source = parse_zboard_source_url(source_url)
    imported = 0
    skipped = 0
    failed = 0
    errors: list[dict[str, Any]] = []
    post_ids: list[int] = []

    items = collect_list_items(None, source, max_pages=max_pages)
    refs = [source_ref(source, item.no) for item in items]
    existing = existing_source_refs(target_board_id, refs) if skip_existing else set()

    for item in items:
        ref = source_ref(source, item.no)
        if ref in existing:
            skipped += 1
            continue

        view_url = build_view_url(source, item.no)
        try:
            html = fetch_html(None, view_url)
            post = parse_view_page(html, source, item.no, is_pinned=item.is_pinned)
        except Exception as exc:
            failed += 1
            errors.append({"no": item.no, "title": item.title, "message": str(exc)[:200]})
            time.sleep(DEFAULT_DELAY_SEC)
            continue

        if dry_run:
            imported += 1
            time.sleep(DEFAULT_DELAY_SEC)
            continue

        created_at = db.utc_now_iso()
        if post.posted_at:
            try:
                from datetime import datetime

                created_at = datetime.strptime(post.posted_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=None).isoformat()
            except ValueError:
                pass

        try:
            post_id = db.execute(
                """
                INSERT INTO posts(
                    board_id, title, body_html, author_username, is_pinned, view_count,
                    status, created_at, updated_at, deleted_at, source_ref
                ) VALUES (?, ?, ?, ?, ?, ?, 'published', ?, ?, NULL, ?)
                """,
                (
                    target_board_id,
                    post.title,
                    post.body_html,
                    author_username,
                    1 if post.is_pinned else 0,
                    post.view_count,
                    created_at,
                    created_at,
                    ref,
                ),
            )
            if mirror_images and post.body_html:
                updated_html = _mirror_images(None, int(post_id), post.body_html, view_url, author_username)
                if updated_html != post.body_html:
                    db.execute(
                        "UPDATE posts SET body_html = ?, updated_at = ? WHERE id = ?",
                        (updated_html, db.utc_now_iso(), post_id),
                    )
            imported += 1
            post_ids.append(int(post_id))
        except Exception as exc:
            failed += 1
            errors.append({"no": item.no, "title": post.title, "message": str(exc)[:200]})

        time.sleep(DEFAULT_DELAY_SEC)

    return {
        "board_id": target_board_id,
        "board_name": board.get("name"),
        "source_url": source_url,
        "source_board_id": source.board_id,
        "total_found": len(items),
        "imported": imported,
        "skipped": skipped,
        "failed": failed,
        "dry_run": dry_run,
        "errors": errors[:30],
        "post_ids": post_ids,
    }


def import_kiccpos_to_board(
    board_name: str = "이지포스",
    author_username: str = "admin",
    **kwargs: Any,
) -> dict[str, Any]:
    board = find_board_by_name(board_name)
    if not board:
        raise ZboardScrapeError(f"'{board_name}' 게시판을 찾을 수 없습니다. 먼저 게시판을 생성해 주세요.")
    return import_scrape(
        int(board["id"]),
        KICCPOS_BOARD_URL,
        author_username,
        **kwargs,
    )
