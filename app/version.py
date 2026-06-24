"""애플리케이션 버전 및 업데이트 내역."""

APP_VERSION = "V1.0.002"
APP_VERSION_CODE = "1.0.002"
RELEASED_AT = "2026-06-23"

CHANGELOG: list[dict] = [
    {
        "version": "V1.0.002",
        "date": "2026-06-23",
        "summary": "게시판 하위 탭·스크랩·사이드바 UX 및 백업 복구 개선",
        "items": [
            "하위 탭 게시판 추가·수정·삭제 및 길게 눌러 드래그 순서 변경",
            "외부 게시판(ZeroBoard) URL 스크랩 미리보기·일괄 가져오기",
            "게시판 생성 저장 오류 수정(숨겨진 탭 폼 검증 차단 해소)",
            "사이드바: 자식 탭 펼침 애니메이션, 카드 호버, 목록 높이 확대·스크롤바 숨김",
            "사이드바: 설정 버튼 톱니 아이콘·게시판 이름 한 줄 배치",
            "글 목록 영역 폭 축소(max-w-3xl)로 가독성 개선",
            "백업 복구 시 부모-자식 게시판 관계(tab_label·parent_board_id) 유지",
            "NAS 배포 시 마운트 경로가 파일로 남은 경우 자동 복구",
        ],
    },
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
