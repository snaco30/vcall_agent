from __future__ import annotations

import bleach
from fastapi import HTTPException, UploadFile

from app.api.board.config import BOARD_CSS_SANITIZER
from app.api.board_db import BOARD_FILES_ROOT, fetch_one
from pathlib import Path

ALLOWED_HTML_TAGS = bleach.sanitizer.ALLOWED_TAGS.union(
    {
        "p",
        "br",
        "hr",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "img",
        "figure",
        "figcaption",
        "span",
        "div",
        "table",
        "thead",
        "tbody",
        "tr",
        "td",
        "th",
        "pre",
        "code",
        "blockquote",
    }
)
ALLOWED_HTML_ATTRS = {
    **bleach.sanitizer.ALLOWED_ATTRIBUTES,
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title", "width", "height"],
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan"],
    "p": ["style"],
    "span": ["style"],
    "div": ["style"],
}
ALLOWED_HTML_PROTOCOLS = {"http", "https", "data"}


def sanitize_slug(slug: str) -> str:
    value = (slug or "").strip().lower()
    if not value:
        raise HTTPException(status_code=400, detail="게시판 slug가 필요합니다.")
    if not all(char.isascii() and (char.isalnum() or char in ("-", "_")) for char in value):
        raise HTTPException(status_code=400, detail="slug는 영문/숫자/-/_만 사용할 수 있습니다.")
    return value


def normalize_post(row: dict) -> dict:
    return {
        **row,
        "is_pinned": bool(row.get("is_pinned", 0)),
        "view_count": int(row.get("view_count", 0) or 0),
    }


def ensure_board(board_id: int) -> dict:
    board = fetch_one("SELECT * FROM boards WHERE id = ?", (board_id,))
    if not board:
        raise HTTPException(status_code=404, detail="게시판을 찾을 수 없습니다.")
    return board


def ensure_post(post_id: int, include_deleted: bool = False) -> dict:
    if include_deleted:
        post = fetch_one("SELECT * FROM posts WHERE id = ?", (post_id,))
    else:
        post = fetch_one("SELECT * FROM posts WHERE id = ? AND deleted_at IS NULL", (post_id,))
    if not post:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")
    return post


def ensure_comment(comment_id: int) -> dict:
    comment = fetch_one("SELECT * FROM comments WHERE id = ? AND deleted_at IS NULL", (comment_id,))
    if not comment:
        raise HTTPException(status_code=404, detail="댓글을 찾을 수 없습니다.")
    return comment


def read_upload_bytes(upload: UploadFile, max_bytes: int) -> bytes:
    content = upload.file.read(max_bytes + 1)
    if not content:
        raise HTTPException(status_code=400, detail="파일이 비어 있습니다.")
    if len(content) > max_bytes:
        raise HTTPException(status_code=400, detail=f"파일 크기는 최대 {max_bytes // (1024 * 1024)}MB까지 가능합니다.")
    return content


def save_file(post_id: int, filename: str, content: bytes) -> Path:
    post_dir = BOARD_FILES_ROOT / str(post_id)
    post_dir.mkdir(parents=True, exist_ok=True)
    file_path = post_dir / filename
    file_path.write_bytes(content)
    return file_path


def sanitize_html(raw_html: str) -> str:
    cleaned = bleach.clean(
        raw_html or "",
        tags=ALLOWED_HTML_TAGS,
        attributes=ALLOWED_HTML_ATTRS,
        protocols=ALLOWED_HTML_PROTOCOLS,
        css_sanitizer=BOARD_CSS_SANITIZER,
        strip=True,
    )
    return cleaned.strip()
