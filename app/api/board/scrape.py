from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth import get_current_user
from app.api.board.common import ensure_board
from app.api.zboard_scrape_service import (
    KICCPOS_BOARD_URL,
    ZboardScrapeError,
    import_scrape,
    preview_scrape,
)

router = APIRouter(tags=["Board Scrape"])


class ScrapePreviewRequest(BaseModel):
    source_url: str = Field(default=KICCPOS_BOARD_URL, min_length=10)
    max_pages: int | None = Field(default=None, ge=1, le=100)


class ScrapeImportRequest(BaseModel):
    source_url: str = Field(default=KICCPOS_BOARD_URL, min_length=10)
    max_pages: int | None = Field(default=None, ge=1, le=100)
    skip_existing: bool = True
    mirror_images: bool = True
    dry_run: bool = False


@router.post("/{board_id}/scrape/preview")
def preview_board_scrape(
    board_id: int,
    payload: ScrapePreviewRequest,
    current_user: str = Depends(get_current_user),
):
    ensure_board(board_id)
    try:
        return preview_scrape(payload.source_url, max_pages=payload.max_pages)
    except ZboardScrapeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"원본 게시판에 연결할 수 없습니다: {exc}") from exc


@router.post("/{board_id}/scrape/import")
def import_board_scrape(
    board_id: int,
    payload: ScrapeImportRequest,
    current_user: str = Depends(get_current_user),
):
    ensure_board(board_id)
    try:
        return import_scrape(
            board_id,
            payload.source_url,
            current_user,
            max_pages=payload.max_pages,
            skip_existing=payload.skip_existing,
            mirror_images=payload.mirror_images,
            dry_run=payload.dry_run,
        )
    except ZboardScrapeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"스크랩 중 오류가 발생했습니다: {exc}") from exc
