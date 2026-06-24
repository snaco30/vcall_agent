from bleach.css_sanitizer import CSSSanitizer

ALLOWED_ATTACHMENT_EXTENSIONS = {".zip", ".txt", ".png", ".pdf"}
ALLOWED_ATTACHMENT_MIME = {
    ".zip": {"application/zip", "application/x-zip-compressed", "application/octet-stream"},
    ".txt": {"text/plain", "application/octet-stream"},
    ".png": {"image/png", "application/octet-stream"},
    ".pdf": {"application/pdf", "application/octet-stream"},
}
MAX_ATTACHMENT_COUNT = 5
MAX_ATTACHMENT_BYTES = 1024 * 1024 * 1024  # 1GB
MAX_INLINE_BYTES = 5 * 1024 * 1024
INLINE_IMAGE_MAX_EDGE = 1600
POSTS_PER_PAGE_DEFAULT = 20
NEW_POST_DAYS = 15
BOARD_CSS_SANITIZER = CSSSanitizer(allowed_css_properties=["text-align"])
