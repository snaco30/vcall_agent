"""애플리케이션 버전 및 업데이트 내역."""

APP_VERSION = "V1.0.001"
APP_VERSION_CODE = "1.0.001"
RELEASED_AT = "2026-06-23"

CHANGELOG: list[dict] = [
    {
        "version": "V1.0.001",
        "date": "2026-06-23",
        "summary": "게시판 센터 및 운영 기능 최초 릴리스",
        "items": [
            "게시판 센터: 다중 게시판, Toast UI Editor 글 작성·댓글·첨부파일(.zip/.txt/.png, 최대 300MB)",
            "게시글 목록 페이지네이션(20건), 최근 15일 새글 빨간점 표시",
            "에디터 이미지 드래그 리사이즈·좌/중앙/우 정렬",
            "게시판 백업/복구(ZIP) 및 서버 파일 저장 경로 안내",
            "엑셀 일괄 등록: 양식 다운로드, 검증 후 저장",
            "게시판 API 기능별 모듈 분리(boards/posts/files/comments/backup/import)",
            "ASP 가맹점 카드형 UI, ASP ID 탭 복사",
            "메인 화면 게시판 바로가기",
        ],
    },
]


def get_version_info() -> dict:
    latest = CHANGELOG[0] if CHANGELOG else {}
    return {
        "version": APP_VERSION,
        "version_code": APP_VERSION_CODE,
        "released_at": RELEASED_AT,
        "summary": latest.get("summary", ""),
        "changelog": CHANGELOG,
    }
