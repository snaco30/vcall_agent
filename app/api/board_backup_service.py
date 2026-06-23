from __future__ import annotations

import io
import json
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.api.board_db import BOARD_DB_PATH, BOARD_FILES_ROOT, fetch_all, get_conn, utc_now_iso

BACKUP_VERSION = 1
BACKUP_PREFIX = "vcall_board_backup"


class BoardBackupError(ValueError):
    """백업/복구 서비스 오류 (라우터에서 HTTPException으로 변환)."""


def _collect_board_data() -> dict[str, Any]:
    return {
        "version": BACKUP_VERSION,
        "exported_at": utc_now_iso(),
        "boards": fetch_all("SELECT * FROM boards ORDER BY id"),
        "posts": fetch_all("SELECT * FROM posts ORDER BY id"),
        "comments": fetch_all("SELECT * FROM comments ORDER BY id"),
        "post_files": fetch_all("SELECT * FROM post_files ORDER BY id"),
    }


def build_backup_zip() -> tuple[bytes, str]:
    payload = _collect_board_data()
    manifest = {
        "version": BACKUP_VERSION,
        "exported_at": payload["exported_at"],
        "board_count": len(payload["boards"]),
        "post_count": len(payload["posts"]),
        "comment_count": len(payload["comments"]),
        "file_count": len(payload["post_files"]),
        "note": f"이미지·첨부파일은 서버 폴더 {BOARD_FILES_ROOT.as_posix()} 를 직접 백업하세요.",
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{BACKUP_PREFIX}_{stamp}.zip"

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        zf.writestr("data.json", json.dumps(payload, ensure_ascii=False, indent=2))
    return buffer.getvalue(), filename


def _rewrite_media_urls(body_html: str, file_id_map: dict[int, int]) -> str:
    if not body_html:
        return ""

    def replacer(match: re.Match[str]) -> str:
        old_id = int(match.group(1))
        new_id = file_id_map.get(old_id)
        if not new_id:
            return match.group(0)
        suffix = match.group(2) or ""
        return f"/api/boards/media/{new_id}{suffix}"

    return re.sub(r"/api/boards/media/(\d+)(\?[^\"'\s>]*)?", replacer, body_html)


def restore_backup_zip(zip_bytes: bytes, mode: str = "merge") -> dict[str, Any]:
    if mode not in ("merge", "replace"):
        raise BoardBackupError("mode는 merge 또는 replace만 가능합니다.")

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            if "data.json" not in zf.namelist():
                raise BoardBackupError("유효하지 않은 백업 파일입니다.")
            payload = json.loads(zf.read("data.json").decode("utf-8"))
    except zipfile.BadZipFile as exc:
        raise BoardBackupError("ZIP 파일이 손상되었습니다.") from exc
    except json.JSONDecodeError as exc:
        raise BoardBackupError("백업 데이터 JSON 파싱 실패") from exc

    boards = payload.get("boards") or []
    posts = payload.get("posts") or []
    comments = payload.get("comments") or []
    post_files = payload.get("post_files") or []

    board_id_map: dict[int, int] = {}
    post_id_map: dict[int, int] = {}
    file_id_map: dict[int, int] = {}

    with get_conn() as conn:
        if mode == "replace":
            conn.execute("DELETE FROM comments")
            conn.execute("DELETE FROM post_files")
            conn.execute("DELETE FROM posts")
            conn.execute("DELETE FROM boards")
            if BOARD_FILES_ROOT.exists():
                shutil.rmtree(BOARD_FILES_ROOT)
            BOARD_FILES_ROOT.mkdir(parents=True, exist_ok=True)

        for board in boards:
            old_id = int(board["id"])
            if mode == "merge":
                existing = conn.execute(
                    "SELECT id FROM boards WHERE slug = ?",
                    (board["slug"],),
                ).fetchone()
                if existing:
                    board_id_map[old_id] = int(existing["id"])
                    continue
            cur = conn.execute(
                """
                INSERT INTO boards(
                    slug, name, description, sort_order, icon, is_active, created_by,
                    created_at, updated_at, parent_board_id, tab_label
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    board["slug"],
                    board["name"],
                    board.get("description") or "",
                    int(board.get("sort_order") or 0),
                    board.get("icon") or "",
                    int(board.get("is_active") or 1),
                    board.get("created_by") or "restore",
                    board.get("created_at") or utc_now_iso(),
                    board.get("updated_at") or utc_now_iso(),
                    board.get("tab_label") or "",
                ),
            )
            board_id_map[old_id] = int(cur.lastrowid)

        for board in boards:
            old_id = int(board["id"])
            new_id = board_id_map.get(old_id)
            if not new_id:
                continue
            old_parent = board.get("parent_board_id")
            new_parent_id = board_id_map.get(int(old_parent)) if old_parent else None
            conn.execute(
                "UPDATE boards SET parent_board_id = ?, tab_label = ? WHERE id = ?",
                (new_parent_id, board.get("tab_label") or "", new_id),
            )

        for post in posts:
            old_id = int(post["id"])
            old_board_id = int(post["board_id"])
            new_board_id = board_id_map.get(old_board_id)
            if not new_board_id:
                continue
            cur = conn.execute(
                """
                INSERT INTO posts(
                    board_id, title, body_html, author_username, is_pinned, view_count,
                    status, created_at, updated_at, deleted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_board_id,
                    post.get("title") or "",
                    post.get("body_html") or "",
                    post.get("author_username") or "restore",
                    int(post.get("is_pinned") or 0),
                    int(post.get("view_count") or 0),
                    post.get("status") or "published",
                    post.get("created_at") or utc_now_iso(),
                    post.get("updated_at") or utc_now_iso(),
                    post.get("deleted_at"),
                ),
            )
            post_id_map[old_id] = int(cur.lastrowid)

        for file_row in post_files:
            old_file_id = int(file_row["id"])
            old_post_id = int(file_row["post_id"])
            new_post_id = post_id_map.get(old_post_id)
            if not new_post_id:
                continue
            cur = conn.execute(
                """
                INSERT INTO post_files(
                    post_id, kind, original_name, stored_name, mime_type, size_bytes,
                    sort_order, created_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_post_id,
                    file_row.get("kind") or "attachment",
                    file_row.get("original_name") or "file",
                    file_row.get("stored_name") or "",
                    file_row.get("mime_type") or "application/octet-stream",
                    int(file_row.get("size_bytes") or 0),
                    int(file_row.get("sort_order") or 0),
                    file_row.get("created_by") or "restore",
                    file_row.get("created_at") or utc_now_iso(),
                ),
            )
            file_id_map[old_file_id] = int(cur.lastrowid)

        for post in posts:
            old_id = int(post["id"])
            new_id = post_id_map.get(old_id)
            if not new_id:
                continue
            body_html = _rewrite_media_urls(post.get("body_html") or "", file_id_map)
            conn.execute("UPDATE posts SET body_html = ? WHERE id = ?", (body_html, new_id))

        for comment in comments:
            old_post_id = int(comment["post_id"])
            new_post_id = post_id_map.get(old_post_id)
            if not new_post_id:
                continue
            conn.execute(
                """
                INSERT INTO comments(post_id, body, author_username, created_at, updated_at, deleted_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    new_post_id,
                    comment.get("body") or "",
                    comment.get("author_username") or "restore",
                    comment.get("created_at") or utc_now_iso(),
                    comment.get("updated_at") or utc_now_iso(),
                    comment.get("deleted_at"),
                ),
            )

        conn.commit()

    files_root = BOARD_FILES_ROOT.as_posix()
    return {
        "mode": mode,
        "restored_boards": len(board_id_map),
        "restored_posts": len(post_id_map),
        "restored_files_meta": len(file_id_map),
        "message": (
            f"글 데이터 복구 완료. 이미지·첨부파일은 서버의 {files_root} 폴더를 백업본으로 직접 복사해 주세요."
        ),
    }


def backup_status() -> dict[str, Any]:
    file_count = sum(1 for path in BOARD_FILES_ROOT.rglob("*") if path.is_file()) if BOARD_FILES_ROOT.exists() else 0
    return {
        "db_path": BOARD_DB_PATH.as_posix(),
        "files_root": BOARD_FILES_ROOT.as_posix(),
        "local_file_count": file_count,
        "db_exists": BOARD_DB_PATH.exists(),
    }
