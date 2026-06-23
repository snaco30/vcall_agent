from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import get_current_user
from app.api.board.common import ensure_comment, ensure_post
from app.api.board.schemas import CommentCreate, CommentUpdate
from app.api.board_db import execute, fetch_all, fetch_one, utc_now_iso

router = APIRouter(tags=["Board Comments"])


@router.get("/posts/{post_id}/comments")
def list_comments(post_id: int, current_user: str = Depends(get_current_user)):
    ensure_post(post_id)
    return fetch_all(
        """
        SELECT id, post_id, body, author_username, created_at, updated_at
        FROM comments
        WHERE post_id = ? AND deleted_at IS NULL
        ORDER BY created_at ASC, id ASC
        """,
        (post_id,),
    )


@router.post("/posts/{post_id}/comments")
def create_comment(post_id: int, payload: CommentCreate, current_user: str = Depends(get_current_user)):
    ensure_post(post_id)
    now = utc_now_iso()
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=400, detail="댓글 내용을 입력해 주세요.")
    comment_id = execute(
        """
        INSERT INTO comments(post_id, body, author_username, created_at, updated_at, deleted_at)
        VALUES (?, ?, ?, ?, ?, NULL)
        """,
        (post_id, body, current_user, now, now),
    )
    return fetch_one(
        "SELECT id, post_id, body, author_username, created_at, updated_at FROM comments WHERE id = ?",
        (comment_id,),
    )


@router.patch("/comments/{comment_id}")
def update_comment(comment_id: int, payload: CommentUpdate, current_user: str = Depends(get_current_user)):
    comment = ensure_comment(comment_id)
    if comment["author_username"] != current_user:
        raise HTTPException(status_code=403, detail="작성자만 댓글을 수정할 수 있습니다.")
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=400, detail="댓글 내용을 입력해 주세요.")
    execute(
        "UPDATE comments SET body = ?, updated_at = ? WHERE id = ?",
        (body, utc_now_iso(), comment_id),
    )
    return fetch_one(
        "SELECT id, post_id, body, author_username, created_at, updated_at FROM comments WHERE id = ?",
        (comment_id,),
    )


@router.delete("/comments/{comment_id}")
def delete_comment(comment_id: int, current_user: str = Depends(get_current_user)):
    comment = ensure_comment(comment_id)
    if comment["author_username"] != current_user:
        raise HTTPException(status_code=403, detail="작성자만 댓글을 삭제할 수 있습니다.")
    now = utc_now_iso()
    execute("UPDATE comments SET deleted_at = ?, updated_at = ? WHERE id = ?", (now, now, comment_id))
    return {"deleted": True}
