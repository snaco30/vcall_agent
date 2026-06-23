"""게시판 API — 기능별 라우터 조합.

각 도메인(게시판·글·파일·댓글·백업)은 독립 모듈로 분리되어 있어
개별 교체·재사용이 가능합니다. URL 경로는 기존과 동일합니다.
"""

from fastapi import APIRouter

from app.api.board.backup import router as backup_router
from app.api.board.boards import router as boards_router
from app.api.board.comments import router as comments_router
from app.api.board.files import router as files_router
from app.api.board.post_import import router as post_import_router
from app.api.board.scrape import router as scrape_router
from app.api.board.posts import router as posts_router

router = APIRouter(prefix="/api/boards")

# 고정 경로가 먼저 매칭되도록 순서 유지
router.include_router(backup_router)
router.include_router(scrape_router)
router.include_router(post_import_router)
router.include_router(posts_router)
router.include_router(files_router)
router.include_router(comments_router)
router.include_router(boards_router)
