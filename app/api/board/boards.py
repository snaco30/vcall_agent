from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.auth import get_current_user
from app.api.board.common import ensure_board, ensure_post, normalize_post, sanitize_slug
from app.api.board.config import NEW_POST_DAYS, POSTS_PER_PAGE_DEFAULT
from app.api.board.schemas import BoardCreate, BoardUpdate, PostCreate
from app.api.board_db import execute, fetch_all, fetch_one, utc_now_iso

router = APIRouter(tags=["Boards"])


@router.get("/")
def list_boards(current_user: str = Depends(get_current_user)):
    new_post_cutoff = (datetime.now(timezone.utc) - timedelta(days=NEW_POST_DAYS)).isoformat()
    boards = fetch_all(
        """
        SELECT
            b.*,
            (
                SELECT COUNT(1)
                FROM posts p
                WHERE p.board_id = b.id
                    AND p.deleted_at IS NULL
                    AND p.status = 'published'
            ) AS post_count,
            (
                SELECT COUNT(1)
                FROM posts p
                WHERE p.board_id = b.id
                    AND p.deleted_at IS NULL
                    AND p.status = 'published'
                    AND p.created_at >= ?
            ) AS new_post_count
        FROM boards b
        ORDER BY b.sort_order ASC, b.id ASC
        """,
        (new_post_cutoff,),
    )
    for board in boards:
        board["is_active"] = bool(board.get("is_active", 0))
        board["post_count"] = int(board.get("post_count", 0) or 0)
        board["new_post_count"] = int(board.get("new_post_count", 0) or 0)
    return boards


@router.post("/")
def create_board(payload: BoardCreate, current_user: str = Depends(get_current_user)):
    now = utc_now_iso()
    slug = sanitize_slug(payload.slug)
    try:
        board_id = execute(
            """
            INSERT INTO boards(slug, name, description, sort_order, icon, is_active, created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                slug,
                payload.name.strip(),
                payload.description.strip(),
                int(payload.sort_order),
                payload.icon.strip(),
                1 if payload.is_active else 0,
                current_user,
                now,
                now,
            ),
        )
    except Exception as exc:
        message = str(exc).lower()
        if "unique" in message:
            raise HTTPException(status_code=409, detail="이미 사용 중인 slug입니다.")
        raise HTTPException(status_code=500, detail="게시판 생성에 실패했습니다.")
    return fetch_one("SELECT * FROM boards WHERE id = ?", (board_id,))


@router.patch("/{board_id}")
def update_board(board_id: int, payload: BoardUpdate, current_user: str = Depends(get_current_user)):
    board = ensure_board(board_id)
    fields: list[str] = []
    values: list[object] = []

    if payload.slug is not None:
        fields.append("slug = ?")
        values.append(sanitize_slug(payload.slug))
    if payload.name is not None:
        fields.append("name = ?")
        values.append(payload.name.strip())
    if payload.description is not None:
        fields.append("description = ?")
        values.append(payload.description.strip())
    if payload.sort_order is not None:
        fields.append("sort_order = ?")
        values.append(int(payload.sort_order))
    if payload.icon is not None:
        fields.append("icon = ?")
        values.append(payload.icon.strip())
    if payload.is_active is not None:
        fields.append("is_active = ?")
        values.append(1 if payload.is_active else 0)

    if not fields:
        return board

    fields.append("updated_at = ?")
    values.append(utc_now_iso())
    values.append(board_id)

    try:
        execute(f"UPDATE boards SET {', '.join(fields)} WHERE id = ?", tuple(values))
    except Exception as exc:
        message = str(exc).lower()
        if "unique" in message:
            raise HTTPException(status_code=409, detail="이미 사용 중인 slug입니다.")
        raise HTTPException(status_code=500, detail="게시판 수정에 실패했습니다.")
    return fetch_one("SELECT * FROM boards WHERE id = ?", (board_id,))


@router.delete("/{board_id}")
def delete_board(board_id: int, current_user: str = Depends(get_current_user)):
    ensure_board(board_id)
    post_count = fetch_one(
        "SELECT COUNT(1) AS count FROM posts WHERE board_id = ? AND deleted_at IS NULL",
        (board_id,),
    )
    count = int((post_count or {}).get("count", 0) or 0)
    if count > 0:
        execute(
            "UPDATE boards SET is_active = 0, updated_at = ? WHERE id = ?",
            (utc_now_iso(), board_id),
        )
        return {"deleted": False, "deactivated": True, "detail": "게시글이 있어 비활성화 처리되었습니다."}

    execute("DELETE FROM boards WHERE id = ?", (board_id,))
    return {"deleted": True, "deactivated": False}


@router.get("/{board_id}/posts")
def list_posts(
    board_id: int,
    q: str = Query("", max_length=120),
    page: int = Query(1, ge=1),
    page_size: int = Query(POSTS_PER_PAGE_DEFAULT, ge=1, le=100),
    current_user: str = Depends(get_current_user),
):
    ensure_board(board_id)
    keyword = q.strip()
    where = "WHERE board_id = ? AND deleted_at IS NULL AND status = 'published'"
    params: list[object] = [board_id]
    if keyword:
        where += " AND (title LIKE ? OR body_html LIKE ?)"
        like = f"%{keyword}%"
        params.extend([like, like])

    total_row = fetch_one(f"SELECT COUNT(1) AS count FROM posts {where}", tuple(params))
    total = int((total_row or {}).get("count", 0) or 0)
    offset = (page - 1) * page_size
    params.extend([page_size, offset])
    rows = fetch_all(
        f"""
        SELECT id, board_id, title, author_username, is_pinned, view_count, status, created_at, updated_at
        FROM posts
        {where}
        ORDER BY is_pinned DESC, created_at DESC
        LIMIT ? OFFSET ?
        """,
        tuple(params),
    )
    for row in rows:
        row["is_pinned"] = bool(row.get("is_pinned", 0))
        row["view_count"] = int(row.get("view_count", 0) or 0)
    return {"items": rows, "total": total, "page": page, "page_size": page_size}


@router.post("/{board_id}/posts")
def create_post_draft(board_id: int, payload: PostCreate, current_user: str = Depends(get_current_user)):
    ensure_board(board_id)
    now = utc_now_iso()
    post_id = execute(
        """
        INSERT INTO posts(board_id, title, body_html, author_username, is_pinned, view_count, status, created_at, updated_at, deleted_at)
        VALUES (?, ?, '', ?, 0, 0, 'draft', ?, ?, NULL)
        """,
        (board_id, payload.title.strip(), current_user, now, now),
    )
    return normalize_post(ensure_post(post_id))
