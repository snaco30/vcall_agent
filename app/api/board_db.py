from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BOARD_DB_PATH = Path(os.getenv("BOARD_DB_PATH", "/data/board.db"))
BOARD_FILES_ROOT = Path(os.getenv("BOARD_FILES_ROOT", "/data/board_files"))


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    lowered = (value or "").strip().lower()
    lowered = re.sub(r"[^a-z0-9가-힣]+", "-", lowered)
    lowered = re.sub(r"-{2,}", "-", lowered).strip("-")
    return lowered or "board"


def get_conn() -> sqlite3.Connection:
    BOARD_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(BOARD_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_board_db() -> None:
    BOARD_FILES_ROOT.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS boards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                description TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                icon TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                board_id INTEGER NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                body_html TEXT NOT NULL DEFAULT '',
                author_username TEXT NOT NULL,
                is_pinned INTEGER NOT NULL DEFAULT 0,
                view_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'draft',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                deleted_at TEXT,
                FOREIGN KEY (board_id) REFERENCES boards(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS post_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                original_name TEXT NOT NULL,
                stored_name TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL,
                body TEXT NOT NULL,
                author_username TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                deleted_at TEXT,
                FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_boards_sort_active ON boards(sort_order, is_active);
            CREATE INDEX IF NOT EXISTS idx_posts_board_status_pin_created
                ON posts(board_id, status, is_pinned DESC, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_post_files_post_kind ON post_files(post_id, kind);
            CREATE INDEX IF NOT EXISTS idx_comments_post_created ON comments(post_id, created_at);
            """
        )


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def fetch_one(query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(query, params).fetchone()
    return row_to_dict(row)


def fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [row_to_dict(row) or {} for row in rows]


def execute(query: str, params: tuple[Any, ...] = ()) -> int:
    with get_conn() as conn:
        cur = conn.execute(query, params)
        conn.commit()
        return cur.lastrowid
