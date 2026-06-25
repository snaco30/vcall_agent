from __future__ import annotations

import io
import mimetypes
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError

from app.api.auth import get_current_user, get_current_user_for_media
from app.api.board.common import ensure_post, read_upload_bytes, save_file
from app.api.board.config import (
    ALLOWED_ATTACHMENT_EXTENSIONS,
    ALLOWED_ATTACHMENT_MIME,
    INLINE_IMAGE_MAX_EDGE,
    MAX_ATTACHMENT_BYTES,
    MAX_ATTACHMENT_COUNT,
    MAX_INLINE_BYTES,
)
from app.api.board_db import BOARD_FILES_ROOT, execute, fetch_one, utc_now_iso

router = APIRouter(tags=["Board Files"])


@router.post("/posts/{post_id}/attachments")
def upload_attachment(post_id: int, file: UploadFile = File(...), current_user: str = Depends(get_current_user)):
    post = ensure_post(post_id)
    if post["author_username"] != current_user:
        raise HTTPException(status_code=403, detail="작성자만 첨부파일을 업로드할 수 있습니다.")

    filename = os.path.basename(file.filename or "").strip()
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_ATTACHMENT_EXTENSIONS:
        raise HTTPException(status_code=400, detail="첨부파일은 .zip, .txt, .png, .pdf만 가능합니다.")

    mime_type = (file.content_type or "").lower()
    if mime_type and mime_type not in ALLOWED_ATTACHMENT_MIME.get(extension, set()):
        raise HTTPException(status_code=400, detail="파일 형식이 허용되지 않습니다.")

    count_row = fetch_one(
        "SELECT COUNT(1) AS count FROM post_files WHERE post_id = ? AND kind = 'attachment'",
        (post_id,),
    )
    attachment_count = int((count_row or {}).get("count", 0) or 0)
    if attachment_count >= MAX_ATTACHMENT_COUNT:
        raise HTTPException(status_code=400, detail="첨부파일은 게시글당 최대 5개까지 업로드할 수 있습니다.")

    content = read_upload_bytes(file, MAX_ATTACHMENT_BYTES)
    stored_name = f"{uuid.uuid4().hex}{extension}"
    save_file(post_id, stored_name, content)
    file_id = execute(
        """
        INSERT INTO post_files(post_id, kind, original_name, stored_name, mime_type, size_bytes, sort_order, created_by, created_at)
        VALUES (?, 'attachment', ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            post_id,
            filename,
            stored_name,
            mime_type or mimetypes.types_map.get(extension, "application/octet-stream"),
            len(content),
            attachment_count + 1,
            current_user,
            utc_now_iso(),
        ),
    )
    return fetch_one(
        "SELECT id, post_id, kind, original_name, mime_type, size_bytes, sort_order, created_at FROM post_files WHERE id = ?",
        (file_id,),
    )


@router.post("/posts/{post_id}/inline-images")
def upload_inline_image(post_id: int, file: UploadFile = File(...), current_user: str = Depends(get_current_user)):
    post = ensure_post(post_id)
    if post["author_username"] != current_user:
        raise HTTPException(status_code=403, detail="작성자만 이미지를 업로드할 수 있습니다.")

    content = read_upload_bytes(file, MAX_INLINE_BYTES)
    try:
        image = Image.open(io.BytesIO(content))
    except UnidentifiedImageError:
        raise HTTPException(status_code=400, detail="이미지 파일만 업로드할 수 있습니다.")

    image.thumbnail((INLINE_IMAGE_MAX_EDGE, INLINE_IMAGE_MAX_EDGE))
    output = io.BytesIO()
    save_format = "PNG" if image.mode in ("RGBA", "LA", "P") else "JPEG"
    if save_format == "JPEG" and image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    image.save(output, format=save_format, quality=88, optimize=True)
    output_bytes = output.getvalue()

    extension = ".png" if save_format == "PNG" else ".jpg"
    stored_name = f"{uuid.uuid4().hex}{extension}"
    save_file(post_id, stored_name, output_bytes)

    file_id = execute(
        """
        INSERT INTO post_files(post_id, kind, original_name, stored_name, mime_type, size_bytes, sort_order, created_by, created_at)
        VALUES (?, 'inline', ?, ?, ?, ?, 0, ?, ?)
        """,
        (
            post_id,
            file.filename or f"inline{extension}",
            stored_name,
            "image/png" if save_format == "PNG" else "image/jpeg",
            len(output_bytes),
            current_user,
            utc_now_iso(),
        ),
    )
    return {
        "id": file_id,
        "url": f"/api/boards/media/{file_id}",
        "mime_type": "image/png" if save_format == "PNG" else "image/jpeg",
    }


@router.get("/media/{file_id}")
def read_media(file_id: int, current_user: str = Depends(get_current_user_for_media)):
    file_row = fetch_one("SELECT * FROM post_files WHERE id = ?", (file_id,))
    if not file_row:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    post = ensure_post(int(file_row["post_id"]))
    file_path = BOARD_FILES_ROOT / str(post["id"]) / file_row["stored_name"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="파일이 존재하지 않습니다.")
    mime_type = file_row["mime_type"] or "application/octet-stream"
    original_name = file_row["original_name"] or file_row["stored_name"]
    inline = mime_type.startswith("application/pdf") or str(original_name).lower().endswith(".pdf")
    return FileResponse(
        str(file_path),
        media_type=mime_type,
        filename=original_name,
        content_disposition_type="inline" if inline else "attachment",
    )


@router.delete("/files/{file_id}")
def delete_file(file_id: int, current_user: str = Depends(get_current_user)):
    file_row = fetch_one("SELECT * FROM post_files WHERE id = ?", (file_id,))
    if not file_row:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    post = ensure_post(int(file_row["post_id"]), include_deleted=True)
    if post["author_username"] != current_user:
        raise HTTPException(status_code=403, detail="작성자만 파일을 삭제할 수 있습니다.")

    file_path = BOARD_FILES_ROOT / str(post["id"]) / file_row["stored_name"]
    if file_path.exists():
        file_path.unlink()
    execute("DELETE FROM post_files WHERE id = ?", (file_id,))
    return {"deleted": True}
