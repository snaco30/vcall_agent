#!/usr/bin/env python3
"""jaypos KICCPOS ZeroBoard → V-CALL 이지포스 게시판 스크랩 CLI."""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.api.board_db import init_board_db  # noqa: E402
from app.api.zboard_scrape_service import (  # noqa: E402
    KICCPOS_BOARD_URL,
    ZboardScrapeError,
    import_kiccpos_to_board,
    preview_scrape,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="jaypos 이지포스 게시판 스크랩")
    parser.add_argument("--board-name", default="이지포스", help="대상 게시판 이름")
    parser.add_argument("--author", default="admin", help="가져온 글 작성자 표시명")
    parser.add_argument("--source-url", default=KICCPOS_BOARD_URL, help="ZeroBoard 목록 URL")
    parser.add_argument("--max-pages", type=int, default=None, help="최대 목록 페이지 수")
    parser.add_argument("--preview", action="store_true", help="미리보기만 수행")
    parser.add_argument("--dry-run", action="store_true", help="DB 저장 없이 파싱만 수행")
    parser.add_argument("--no-skip-existing", action="store_true", help="이미 가져온 글도 다시 시도")
    parser.add_argument("--no-mirror-images", action="store_true", help="이미지 복사 생략")
    args = parser.parse_args()

    init_board_db()

    try:
        if args.preview:
            result = preview_scrape(args.source_url, max_pages=args.max_pages)
            print(f"원본: {result['board_id']} / 총 {result['total_posts']}건 (고정 {result['pinned_count']}건)")
            for title in result.get("sample_titles", []):
                print(f"  - {title}")
            return 0

        result = import_kiccpos_to_board(
            board_name=args.board_name,
            author_username=args.author,
            source_url=args.source_url,
            max_pages=args.max_pages,
            skip_existing=not args.no_skip_existing,
            mirror_images=not args.no_mirror_images,
            dry_run=args.dry_run,
        )
    except ZboardScrapeError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1

    print(
        f"완료: 대상={result['board_name']}({result['board_id']}), "
        f"발견={result['total_found']}, 성공={result['imported']}, "
        f"건너뜀={result['skipped']}, 실패={result['failed']}"
    )
    for error in result.get("errors", []):
        print(f"  실패 no={error.get('no')}: {error.get('message')}", file=sys.stderr)
    return 0 if result["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
