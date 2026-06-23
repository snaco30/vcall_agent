#!/usr/bin/env python3
"""게시판 백업/복구 기능 테스트 (격리 DB + 운영 DB 읽기 전용 검증)."""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

# 프로젝트 루트를 path에 추가 (로컬 실행 시)
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _seed_parent_child_boards(board_db) -> dict:
    now = board_db.utc_now_iso()
    with board_db.get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO boards(
                slug, name, description, sort_order, icon, is_active, created_by,
                created_at, updated_at, parent_board_id, tab_label
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
            """,
            ("test-parent", "부모게시판", "", 0, "", 1, "tester", now, now, "기본탭"),
        )
        parent_id = int(cur.lastrowid)
        cur = conn.execute(
            """
            INSERT INTO boards(
                slug, name, description, sort_order, icon, is_active, created_by,
                created_at, updated_at, parent_board_id, tab_label
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("test-child", "자식게시판", "", 1, "", 1, "tester", now, now, parent_id, "자식탭"),
        )
        child_id = int(cur.lastrowid)
        conn.commit()
    return {"parent_id": parent_id, "child_id": child_id}


def _seed_sample_data(board_db, board_backup) -> dict:
    now = board_db.utc_now_iso()
    with board_db.get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO boards(slug, name, description, sort_order, icon, is_active, created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("test-backup", "백업테스트", "desc", 0, "", 1, "tester", now, now),
        )
        board_id = int(cur.lastrowid)
        cur = conn.execute(
            """
            INSERT INTO posts(board_id, title, body_html, author_username, is_pinned, view_count, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (board_id, "테스트 글", "<p>hello</p>", "tester", 0, 0, "published", now, now),
        )
        post_id = int(cur.lastrowid)
        stored_name = "sample.txt"
        file_dir = board_db.BOARD_FILES_ROOT / str(post_id)
        file_dir.mkdir(parents=True, exist_ok=True)
        (file_dir / stored_name).write_text("backup file content", encoding="utf-8")
        cur = conn.execute(
            """
            INSERT INTO post_files(post_id, kind, original_name, stored_name, mime_type, size_bytes, sort_order, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (post_id, "attachment", "sample.txt", stored_name, "text/plain", 19, 0, "tester", now),
        )
        file_id = int(cur.lastrowid)
        cur = conn.execute(
            """
            INSERT INTO comments(post_id, body, author_username, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (post_id, "댓글", "tester", now, now),
        )
        conn.commit()
    return {"board_id": board_id, "post_id": post_id, "file_id": file_id}


def _counts(board_db) -> dict[str, int]:
    return {
        "boards": len(board_db.fetch_all("SELECT id FROM boards")),
        "posts": len(board_db.fetch_all("SELECT id FROM posts")),
        "comments": len(board_db.fetch_all("SELECT id FROM comments")),
        "post_files": len(board_db.fetch_all("SELECT id FROM post_files")),
    }


def run_isolated_roundtrip() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="board_backup_test_"))
    os.environ["BOARD_DB_PATH"] = str(tmp / "board.db")
    os.environ["BOARD_FILES_ROOT"] = str(tmp / "board_files")

    # 모듈 재로드 (환경 변수 반영)
    import importlib
    from app.api import board_db, board_backup

    importlib.reload(board_db)
    importlib.reload(board_backup)

    board_db.init_board_db()
    seed = _seed_sample_data(board_db, board_backup)
    before = _counts(board_db)

    status = board_backup.backup_status()
    assert status["db_exists"], "DB 파일이 생성되어야 합니다"
    assert status["local_file_count"] == 1, f"첨부파일 1개 기대, 실제 {status['local_file_count']}"
    assert status["db_path"].endswith("board.db")
    assert status["files_root"].endswith("board_files")

    zip_bytes, filename = board_backup.build_backup_zip()
    assert filename.startswith("vcall_board_backup_"), filename
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
        assert names == {"manifest.json", "data.json"}, names
        manifest = json.loads(zf.read("manifest.json"))
        data = json.loads(zf.read("data.json"))
    assert manifest["post_count"] == 1
    assert len(data["boards"]) == 1
    assert len(data["posts"]) == 1

    # DB 비우기 후 merge 복구
    with board_db.get_conn() as conn:
        conn.execute("DELETE FROM comments")
        conn.execute("DELETE FROM post_files")
        conn.execute("DELETE FROM posts")
        conn.execute("DELETE FROM boards")
        conn.commit()
    shutil.rmtree(board_db.BOARD_FILES_ROOT)
    board_db.BOARD_FILES_ROOT.mkdir(parents=True, exist_ok=True)
    assert _counts(board_db)["boards"] == 0

    result = board_backup.restore_backup_zip(zip_bytes, mode="merge")
    assert result["restored_boards"] == 1
    assert result["restored_posts"] == 1
    after_merge = _counts(board_db)
    assert after_merge == before, f"merge 복구 후 건수 불일치: {after_merge} vs {before}"

    # replace 모드: 기존 삭제 후 동일 ZIP으로 복구
    result2 = board_backup.restore_backup_zip(zip_bytes, mode="replace")
    assert result2["restored_boards"] == 1
    after_replace = _counts(board_db)
    assert after_replace == before

    print("[OK] 격리 DB 백업 ZIP 생성 / merge·replace 복구 성공")
    print(f"     시드 post_id={seed['post_id']}, status paths: {status['db_path']}, {status['files_root']}/")
    shutil.rmtree(tmp, ignore_errors=True)


def run_parent_child_restore() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="board_backup_tabs_"))
    os.environ["BOARD_DB_PATH"] = str(tmp / "board.db")
    os.environ["BOARD_FILES_ROOT"] = str(tmp / "board_files")

    import importlib
    from app.api import board_db, board_backup_service as board_backup

    importlib.reload(board_db)
    importlib.reload(board_backup)

    board_db.init_board_db()
    seed = _seed_parent_child_boards(board_db)
    zip_bytes, _ = board_backup.build_backup_zip()

    with board_db.get_conn() as conn:
        conn.execute("DELETE FROM boards")
        conn.commit()

    board_backup.restore_backup_zip(zip_bytes, mode="replace")
    child = board_db.fetch_one("SELECT parent_board_id, tab_label FROM boards WHERE slug = 'test-child'")
    parent = board_db.fetch_one("SELECT id, tab_label FROM boards WHERE slug = 'test-parent'")
    assert child and parent, "복구 후 게시판이 있어야 합니다"
    assert int(child["parent_board_id"]) == int(parent["id"]), child
    assert child["tab_label"] == "자식탭"
    assert parent["tab_label"] == "기본탭"
    print(f"[OK] 부모-자식 탭 관계 복구 (parent={seed['parent_id']} child={seed['child_id']})")
    shutil.rmtree(tmp, ignore_errors=True)


def run_production_readonly() -> None:
    prod_db = Path("/data/board.db")
    if not prod_db.exists():
        print("[SKIP] 운영 DB 없음 (/data/board.db)")
        return

    from app.api import board_db

    board_db.init_board_db()
    from app.api import board_backup_service as board_backup

    status = board_backup.backup_status()
    counts = _counts(board_db)
    zip_bytes, filename = board_backup.build_backup_zip()
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        data = json.loads(zf.read("data.json"))

    assert manifest["board_count"] == counts["boards"]
    assert manifest["post_count"] == counts["posts"]
    assert manifest["comment_count"] == counts["comments"]
    assert manifest["file_count"] == counts["post_files"]
    assert len(data["boards"]) == counts["boards"]

    print("[OK] 운영 DB 읽기 전용 백업 검증")
    print(f"     boards={counts['boards']} posts={counts['posts']} files_meta={counts['post_files']} file_disk={status['local_file_count']}")
    print(f"     ZIP={filename} ({len(zip_bytes)} bytes)")
    print(f"     저장경로 DB={status['db_path']} files={status['files_root']}/")


def main() -> int:
    errors: list[str] = []
    for name, fn in (
        ("production", run_production_readonly),
        ("isolated", run_isolated_roundtrip),
        ("parent_child", run_parent_child_restore),
    ):
        try:
            fn()
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            print(f"[FAIL] {name}: {exc}", file=sys.stderr)

    if errors:
        print(f"\n실패 {len(errors)}건", file=sys.stderr)
        return 1
    print("\n모든 백업/복구 테스트 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
