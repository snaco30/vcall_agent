from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.auth import get_current_user
from app.api.board.common import ensure_board, ensure_post, normalize_post, sanitize_slug
from app.api.board.config import NEW_POST_DAYS, POSTS_PER_PAGE_DEFAULT
from app.api.board.schemas import BoardCreate, BoardReorder, BoardTabCreate, BoardTabUpdate, BoardUpdate, PostCreate
from app.api.board_db import POST_LIST_ORDER_SQL, execute, fetch_all, fetch_one, utc_now_iso

router = APIRouter(tags=["Boards"])


def _draft_preview(body_html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", body_html or "")
    return " ".join(text.split())[:120]


def _tab_summary(board: dict) -> dict:
    label = (board.get("tab_label") or board.get("name") or "").strip()
    return {
        "id": int(board["id"]),
        "name": board.get("name") or "",
        "tab_label": label,
        "slug": board.get("slug") or "",
        "post_count": int(board.get("post_count", 0) or 0),
        "new_post_count": int(board.get("new_post_count", 0) or 0),
        "is_active": bool(board.get("is_active", 0)),
    }


def _attach_board_tabs(boards: list[dict]) -> list[dict]:
    children_by_parent: dict[int, list[dict]] = {}
    for board in boards:
        parent_id = board.get("parent_board_id")
        if parent_id:
            children_by_parent.setdefault(int(parent_id), []).append(board)

    top_level = [board for board in boards if not board.get("parent_board_id")]
    for board in top_level:
        children = sorted(
            children_by_parent.get(int(board["id"]), []),
            key=lambda row: (int(row.get("sort_order", 0) or 0), int(row["id"])),
        )
        if children:
            board["tabs"] = [_tab_summary(board)] + [_tab_summary(child) for child in children]
            board["post_count"] = sum(tab["post_count"] for tab in board["tabs"])
            board["new_post_count"] = sum(tab["new_post_count"] for tab in board["tabs"])
        else:
            board["tabs"] = []
    return top_level


def _next_sort_order(parent_board_id: int | None = None) -> int:
    if parent_board_id is None:
        row = fetch_one(
            "SELECT COALESCE(MAX(sort_order), -1) AS max_order FROM boards WHERE parent_board_id IS NULL",
            (),
        )
    else:
        row = fetch_one(
            "SELECT COALESCE(MAX(sort_order), -1) AS max_order FROM boards WHERE parent_board_id = ?",
            (parent_board_id,),
        )
    return int((row or {}).get("max_order", -1) or -1) + 1


def _validate_parent_board(parent_id: int | None, board_id: int | None = None) -> None:
    if parent_id is None:
        return
    if board_id is not None and parent_id == board_id:
        raise HTTPException(status_code=400, detail="자기 자신을 상위 게시판으로 지정할 수 없습니다.")
    parent = ensure_board(parent_id)
    if parent.get("parent_board_id"):
        raise HTTPException(status_code=400, detail="하위 탭 게시판 아래에는 탭을 추가할 수 없습니다.")


def _board_with_child_tabs(board_id: int) -> dict:
    board = ensure_board(board_id)
    board["is_active"] = bool(board.get("is_active", 0))
    if board.get("parent_board_id") is not None:
        board["parent_board_id"] = int(board["parent_board_id"])
    children = fetch_all(
        """
        SELECT
            b.*,
            (
                SELECT COUNT(1)
                FROM posts p
                WHERE p.board_id = b.id AND p.deleted_at IS NULL AND p.status = 'published'
            ) AS post_count
        FROM boards b
        WHERE b.parent_board_id = ?
        ORDER BY b.sort_order ASC, b.id ASC
        """,
        (board_id,),
    )
    for child in children:
        child["is_active"] = bool(child.get("is_active", 0))
        child["post_count"] = int(child.get("post_count", 0) or 0)
    board["child_tabs"] = children
    return board


@router.post("/reorder")
def reorder_boards(payload: BoardReorder, current_user: str = Depends(get_current_user)):
    seen: set[int] = set()
    for board_id in payload.board_ids:
        if board_id in seen:
            raise HTTPException(status_code=400, detail="중복된 게시판 ID가 있습니다.")
        seen.add(board_id)
        board = fetch_one("SELECT id, parent_board_id FROM boards WHERE id = ?", (board_id,))
        if not board:
            raise HTTPException(status_code=404, detail=f"게시판(id={board_id})을 찾을 수 없습니다.")
        if board.get("parent_board_id"):
            raise HTTPException(status_code=400, detail="최상위 게시판만 순서를 변경할 수 있습니다.")

    now = utc_now_iso()
    for index, board_id in enumerate(payload.board_ids):
        execute(
            "UPDATE boards SET sort_order = ?, updated_at = ? WHERE id = ? AND parent_board_id IS NULL",
            (index, now, board_id),
        )
    return {"ok": True, "board_ids": payload.board_ids}


@router.get("/{board_id}")
def get_board(board_id: int, current_user: str = Depends(get_current_user)):
    return _board_with_child_tabs(board_id)


@router.post("/{board_id}/tabs")
def create_board_tab(
    board_id: int,
    payload: BoardTabCreate,
    current_user: str = Depends(get_current_user),
):
    parent = ensure_board(board_id)
    if parent.get("parent_board_id"):
        raise HTTPException(status_code=400, detail="하위 탭에서는 탭을 추가할 수 없습니다.")

    now = utc_now_iso()
    slug = sanitize_slug(payload.slug)
    sort_order = int(payload.sort_order)
    if sort_order <= 0:
        sort_order = _next_sort_order(board_id)
    try:
        tab_id = execute(
            """
            INSERT INTO boards(
                slug, name, description, sort_order, icon, is_active, created_by,
                created_at, updated_at, parent_board_id, tab_label
            )
            VALUES (?, ?, ?, ?, '', ?, ?, ?, ?, ?, ?)
            """,
            (
                slug,
                payload.name.strip(),
                payload.description.strip(),
                sort_order,
                1 if payload.is_active else 0,
                current_user,
                now,
                now,
                board_id,
                (payload.tab_label or payload.name).strip(),
            ),
        )
    except Exception as exc:
        message = str(exc).lower()
        if "unique" in message:
            raise HTTPException(status_code=409, detail="이미 사용 중인 slug입니다.")
        raise HTTPException(status_code=500, detail="하위 탭 생성에 실패했습니다.") from exc
    return fetch_one("SELECT * FROM boards WHERE id = ?", (tab_id,))


@router.patch("/{board_id}/tabs/{tab_id}")
def update_board_tab(
    board_id: int,
    tab_id: int,
    payload: BoardTabUpdate,
    current_user: str = Depends(get_current_user),
):
    ensure_board(board_id)
    tab = fetch_one("SELECT * FROM boards WHERE id = ? AND parent_board_id = ?", (tab_id, board_id))
    if not tab:
        raise HTTPException(status_code=404, detail="하위 탭을 찾을 수 없습니다.")

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
    if payload.is_active is not None:
        fields.append("is_active = ?")
        values.append(1 if payload.is_active else 0)
    if payload.tab_label is not None:
        fields.append("tab_label = ?")
        values.append(payload.tab_label.strip())

    if not fields:
        return tab

    fields.append("updated_at = ?")
    values.append(utc_now_iso())
    values.append(tab_id)
    try:
        execute(f"UPDATE boards SET {', '.join(fields)} WHERE id = ?", tuple(values))
    except Exception as exc:
        message = str(exc).lower()
        if "unique" in message:
            raise HTTPException(status_code=409, detail="이미 사용 중인 slug입니다.")
        raise HTTPException(status_code=500, detail="하위 탭 수정에 실패했습니다.") from exc
    return fetch_one("SELECT * FROM boards WHERE id = ?", (tab_id,))


@router.delete("/{board_id}/tabs/{tab_id}")
def delete_board_tab(board_id: int, tab_id: int, current_user: str = Depends(get_current_user)):
    ensure_board(board_id)
    tab = fetch_one("SELECT * FROM boards WHERE id = ? AND parent_board_id = ?", (tab_id, board_id))
    if not tab:
        raise HTTPException(status_code=404, detail="하위 탭을 찾을 수 없습니다.")

    post_count = fetch_one(
        "SELECT COUNT(1) AS count FROM posts WHERE board_id = ? AND deleted_at IS NULL",
        (tab_id,),
    )
    count = int((post_count or {}).get("count", 0) or 0)
    if count > 0:
        execute(
            "UPDATE boards SET is_active = 0, updated_at = ? WHERE id = ?",
            (utc_now_iso(), tab_id),
        )
        return {"deleted": False, "deactivated": True, "detail": "게시글이 있어 비활성화 처리되었습니다."}

    execute("DELETE FROM boards WHERE id = ?", (tab_id,))
    return {"deleted": True, "deactivated": False}


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
        if board.get("parent_board_id") is not None:
            board["parent_board_id"] = int(board["parent_board_id"])
    return _attach_board_tabs(boards)


@router.post("/")
def create_board(payload: BoardCreate, current_user: str = Depends(get_current_user)):
    _validate_parent_board(payload.parent_board_id)
    now = utc_now_iso()
    slug = sanitize_slug(payload.slug)
    sort_order = int(payload.sort_order)
    if sort_order <= 0:
        sort_order = _next_sort_order(payload.parent_board_id)
    try:
        board_id = execute(
            """
            INSERT INTO boards(
                slug, name, description, sort_order, icon, is_active, created_by,
                created_at, updated_at, parent_board_id, tab_label
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                slug,
                payload.name.strip(),
                payload.description.strip(),
                sort_order,
                payload.icon.strip(),
                1 if payload.is_active else 0,
                current_user,
                now,
                now,
                payload.parent_board_id,
                payload.tab_label.strip(),
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
    if payload.parent_board_id is not None:
        _validate_parent_board(payload.parent_board_id, board_id)
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
    if payload.parent_board_id is not None:
        fields.append("parent_board_id = ?")
        values.append(payload.parent_board_id)
    if payload.tab_label is not None:
        fields.append("tab_label = ?")
        values.append(payload.tab_label.strip())

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
    child_count = fetch_one(
        "SELECT COUNT(1) AS count FROM boards WHERE parent_board_id = ?",
        (board_id,),
    )
    if int((child_count or {}).get("count", 0) or 0) > 0:
        raise HTTPException(status_code=400, detail="하위 탭이 있으면 먼저 삭제해 주세요.")
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


@router.get("/{board_id}/posts/drafts")
def list_post_drafts(board_id: int, current_user: str = Depends(get_current_user)):
    ensure_board(board_id)
    rows = fetch_all(
        """
        SELECT id, board_id, title, body_html, author_username, is_pinned, view_count, status, created_at, updated_at
        FROM posts
        WHERE board_id = ? AND author_username = ? AND deleted_at IS NULL AND status = 'draft'
        ORDER BY updated_at DESC, id DESC
        LIMIT 30
        """,
        (board_id, current_user),
    )
    items = []
    for row in rows:
        post = normalize_post(row)
        post["preview"] = _draft_preview(row.get("body_html") or "")
        items.append(post)
    return {"items": items}


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
        SELECT id, board_id, title, author_username, is_pinned, view_count, status, created_at, updated_at,
               (SELECT COUNT(1) FROM post_files WHERE post_id = posts.id AND kind = 'attachment') AS attachment_count
        FROM posts
        {where}
        ORDER BY {POST_LIST_ORDER_SQL}
        LIMIT ? OFFSET ?
        """,
        tuple(params),
    )
    for row in rows:
        row["is_pinned"] = bool(row.get("is_pinned", 0))
        row["view_count"] = int(row.get("view_count", 0) or 0)
        row["attachment_count"] = int(row.get("attachment_count", 0) or 0)
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
