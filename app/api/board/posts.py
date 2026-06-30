from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.auth import get_current_user
from app.api.board.common import ensure_board, ensure_post, normalize_post, sanitize_html
from app.api.board.config import POSTS_PER_PAGE_DEFAULT
from app.api.board.schemas import PostUpdate
from app.api.board_db import POST_SORT_DATETIME_SQL, execute, fetch_all, fetch_one, utc_now_iso

router = APIRouter(tags=["Board Posts"])

GLOBAL_POST_ORDER_SQL = f"p.is_pinned DESC, {POST_SORT_DATETIME_SQL.replace('created_at', 'p.created_at')} DESC, p.id DESC"


@router.get("/posts/search")
def search_posts_global(
    q: str = Query("", max_length=120),
    page: int = Query(1, ge=1),
    page_size: int = Query(POSTS_PER_PAGE_DEFAULT, ge=1, le=100),
    current_user: str = Depends(get_current_user),
):
    keyword = q.strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="검색어를 입력해 주세요.")

    where = "WHERE p.deleted_at IS NULL AND p.status = 'published' AND b.is_active = 1"
    like = f"%{keyword}%"
    params: list[object] = [like, like]
    where += " AND (p.title LIKE ? OR p.body_html LIKE ?)"

    total_row = fetch_one(
        f"""
        SELECT COUNT(1) AS count
        FROM posts p
        INNER JOIN boards b ON b.id = p.board_id
        {where}
        """,
        tuple(params),
    )
    total = int((total_row or {}).get("count", 0) or 0)
    offset = (page - 1) * page_size
    query_params = list(params) + [page_size, offset]
    rows = fetch_all(
        f"""
        SELECT
            p.id, p.board_id, p.title, p.author_username, p.is_pinned, p.view_count,
            p.status, p.created_at, p.updated_at,
            (SELECT COUNT(1) FROM post_files WHERE post_id = p.id AND kind = 'attachment') AS attachment_count
        FROM posts p
        INNER JOIN boards b ON b.id = p.board_id
        {where}
        ORDER BY {GLOBAL_POST_ORDER_SQL}
        LIMIT ? OFFSET ?
        """,
        tuple(query_params),
    )
    for row in rows:
        row["is_pinned"] = bool(row.get("is_pinned", 0))
        row["view_count"] = int(row.get("view_count", 0) or 0)
        row["attachment_count"] = int(row.get("attachment_count", 0) or 0)
    return {"items": rows, "total": total, "page": page, "page_size": page_size}


@router.get("/posts/{post_id}")
def get_post_detail(
    post_id: int,
    with_view_count: bool = Query(True),
    current_user: str = Depends(get_current_user),
):
    post = ensure_post(post_id)
    if with_view_count:
        execute("UPDATE posts SET view_count = view_count + 1 WHERE id = ?", (post_id,))
        post = ensure_post(post_id)

    files = fetch_all(
        """
        SELECT id, post_id, kind, original_name, mime_type, size_bytes, sort_order, created_at
        FROM post_files
        WHERE post_id = ?
        ORDER BY kind ASC, sort_order ASC, id ASC
        """,
        (post_id,),
    )
    comments = fetch_all(
        """
        SELECT id, post_id, body, author_username, created_at, updated_at
        FROM comments
        WHERE post_id = ? AND deleted_at IS NULL
        ORDER BY created_at ASC, id ASC
        """,
        (post_id,),
    )
    return {
        "post": normalize_post(post),
        "files": files,
        "comments": comments,
    }


@router.patch("/posts/{post_id}")
def update_post(post_id: int, payload: PostUpdate, current_user: str = Depends(get_current_user)):
    post = ensure_post(post_id)
    if post["author_username"] != current_user:
        raise HTTPException(status_code=403, detail="작성자만 게시글을 수정할 수 있습니다.")

    status = (payload.status or "published").strip().lower()
    if status not in ("draft", "published"):
        raise HTTPException(status_code=400, detail="status는 draft 또는 published만 가능합니다.")

    body_html = sanitize_html(payload.body_html)
    title = (payload.title or "").strip()
    if status == "published":
        if not title:
            raise HTTPException(status_code=400, detail="제목을 입력해 주세요.")
        if not body_html:
            raise HTTPException(status_code=400, detail="본문을 입력해 주세요.")

    board_id = int(post["board_id"])
    if payload.board_id is not None:
        target_board_id = int(payload.board_id)
        if target_board_id != board_id:
            target_board = ensure_board(target_board_id)
            if not bool(target_board.get("is_active", 0)):
                raise HTTPException(status_code=400, detail="비활성 게시판으로는 이동할 수 없습니다.")
            board_id = target_board_id

    now = utc_now_iso()
    was_draft = (post.get("status") or "").strip().lower() == "draft"
    created_at = now if was_draft and status == "published" else post["created_at"]
    execute(
        """
        UPDATE posts
        SET board_id = ?, title = ?, body_html = ?, is_pinned = ?, status = ?, updated_at = ?, created_at = ?
        WHERE id = ?
        """,
        (board_id, title, body_html, 1 if payload.is_pinned else 0, status, now, created_at, post_id),
    )
    return normalize_post(ensure_post(post_id))


@router.delete("/posts/{post_id}")
def delete_post(post_id: int, current_user: str = Depends(get_current_user)):
    post = ensure_post(post_id)
    if post["author_username"] != current_user:
        raise HTTPException(status_code=403, detail="작성자만 게시글을 삭제할 수 있습니다.")

    execute(
        "UPDATE posts SET deleted_at = ?, updated_at = ? WHERE id = ?",
        (utc_now_iso(), utc_now_iso(), post_id),
    )
    return {"deleted": True}
