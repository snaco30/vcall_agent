import os
import sqlite3
from pathlib import Path


def get_asp_db_path() -> str:
    env_path = os.getenv("ASP_DB_PATH")
    if env_path:
        return env_path
    if Path("/data").is_dir():
        return "/data/asp_merchants.db"
    return "data/asp_merchants.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS asp_merchants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    merchant_name TEXT NOT NULL DEFAULT '',
    saup_no TEXT NOT NULL DEFAULT '',
    presi_name TEXT NOT NULL DEFAULT '',
    tel_no TEXT NOT NULL DEFAULT '',
    addr TEXT NOT NULL DEFAULT '',
    asp_provider TEXT NOT NULL DEFAULT '',
    merchant_id TEXT NOT NULL DEFAULT '',
    terminal_id TEXT NOT NULL DEFAULT '',
    asp_join_date TEXT NOT NULL DEFAULT '',
    usage_status TEXT NOT NULL DEFAULT '',
    van_type TEXT NOT NULL DEFAULT '',
    damdang TEXT NOT NULL DEFAULT '',
    bigo TEXT NOT NULL DEFAULT '',
    extras TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_asp_merchants_name ON asp_merchants(merchant_name);
"""


def get_connection() -> sqlite3.Connection:
    db_path = Path(get_asp_db_path())
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _harden_db_file_permissions() -> None:
    db_path = Path(get_asp_db_path())
    if not db_path.is_file():
        return
    try:
        os.chmod(db_path, 0o600)
    except OSError:
        pass


def init_asp_db() -> None:
    with get_connection() as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    _harden_db_file_permissions()


def asp_row_count() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM asp_merchants").fetchone()
        return int(row["cnt"]) if row else 0
