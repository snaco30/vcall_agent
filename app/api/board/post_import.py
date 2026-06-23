from __future__ import annotations

import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.api.auth import get_current_user
from app.api.board.common import ensure_board
from app.api.board.post_import_service import (
    PostImportError,
    build_import_template_xlsx,
    import_posts_from_rows,
    parse_import_xlsx,
    validate_import_xlsx,
)

router = APIRouter(tags=["Board Post Import"])


@router.get("/{board_id}/posts/import-template")
def download_post_import_template(board_id: int, current_user: str = Depends(get_current_user)):
    ensure_board(board_id)
    content, filename = build_import_template_xlsx()
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{board_id}/posts/import/validate")
async def validate_posts_import_excel(
    board_id: int,
    file: UploadFile = File(...),
    current_user: str = Depends(get_current_user),
):
    ensure_board(board_id)
    filename = (file.filename or "").lower()
    if not filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="엑셀 파일(.xlsx)만 업로드할 수 있습니다.")

    raw = await file.read()
    return validate_import_xlsx(raw)


@router.post("/{board_id}/posts/import")
async def import_posts_from_excel(
    board_id: int,
    file: UploadFile = File(...),
    current_user: str = Depends(get_current_user),
):
    ensure_board(board_id)
    filename = (file.filename or "").lower()
    if not filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="엑셀 파일(.xlsx)만 업로드할 수 있습니다.")

    raw = await file.read()
    try:
        rows = parse_import_xlsx(raw)
        result = import_posts_from_rows(board_id, rows, current_user)
    except PostImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return result
