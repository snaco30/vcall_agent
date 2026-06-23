from __future__ import annotations

import io

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.api.auth import get_current_user
from app.api.board_backup_service import (
    BoardBackupError,
    backup_status,
    build_backup_zip,
    restore_backup_zip,
)

router = APIRouter(tags=["Board Backup"])


@router.get("/backup/status")
def get_backup_status(current_user: str = Depends(get_current_user)):
    return backup_status()


@router.get("/backup/download")
def download_board_backup(current_user: str = Depends(get_current_user)):
    content, filename = build_backup_zip()
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/backup/restore")
async def restore_board_backup(
    file: UploadFile = File(...),
    mode: str = Query("merge", pattern="^(merge|replace)$"),
    current_user: str = Depends(get_current_user),
):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="백업 파일이 비어 있습니다.")
    try:
        return restore_backup_zip(raw, mode=mode)
    except BoardBackupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
