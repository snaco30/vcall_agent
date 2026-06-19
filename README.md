# V-CALL 가맹점 관리 콘솔

V-CALL 관리자용 **가맹점 마스터 조회** 및 **통화 이력** 웹 콘솔입니다.  
Microsoft Access MDB(`vanpro97_call.mdb`)를 읽어 가맹점 검색, 통화 내역 열람, 수신 통화 목록 조회를 제공합니다.

## 주요 기능

- **가맹점 검색** — 상호명, 전화번호, 대표자명, 사업자등록번호로 조회
- **통화 이력** — 가맹점 카드 클릭 시 `TCALLCONTENT2` 기반 통화 내역 모달
- **수신 통화 목록** — 날짜별 수신(인입) 통화 필터 및 조회
- **MDB 동기화** — SMB 공유 원본에서 로컬 복사본으로 동기화 (웹 UI·스크립트·systemd timer)
- **JWT 인증** — 관리자 계정 로그인 후 API 접근

## 기술 스택

| 구분 | 기술 |
|------|------|
| 백엔드 | Python 3.10, FastAPI, Uvicorn |
| 인증 | PyJWT |
| 데이터 | MDB (`mdb-export` / mdbtools) |
| 프론트엔드 | HTML, Tailwind CSS (CDN), Vanilla JS |
| 배포 | Docker |

## 아키텍처

```mermaid
flowchart LR
    subgraph client [Browser]
        UI[index.html]
    end
    subgraph app [FastAPI :7002]
        Auth[/api/auth]
        Merchants[/api/merchants]
        History[/api/history]
        Sync[/api/sync]
    end
    subgraph data [Data]
        LocalMDB["/data/vanpro97_call.mdb"]
        SMB["SMB vcallmanager1"]
    end
    UI --> Auth
    UI --> Merchants
    UI --> History
    UI --> Sync
    Merchants --> LocalMDB
    History --> LocalMDB
    Sync --> LocalMDB
    Sync --> SMB
    scripts[sync-mdb.sh / timer] --> SMB
    scripts --> LocalMDB
```

## 프로젝트 구조

```
vcall_agent/
├── app/
│   ├── main.py              # FastAPI 앱 진입점
│   ├── index.html           # 관리 콘솔 UI
│   └── api/
│       ├── auth.py          # 로그인 / JWT
│       ├── merchants.py     # 가맹점 검색 (TMER2)
│       ├── history.py       # 통화 이력·수신 통화 (TCALLCONTENT2)
│       ├── sync.py          # MDB 동기화 상태·트리거
│       └── deps.py
├── data/                    # 로컬 MDB 복사본 (git 제외)
├── mnt/vcallmanager1/       # SMB 마운트 지점 (git 제외)
├── scripts/
│   ├── sync-mdb.sh          # MDB 복사 스크립트
│   ├── mount-mdb-share.sh   # SMB CIFS 마운트
│   ├── install-mdb-sync-timer.sh
│   └── systemd/
├── deploy.sh                # Docker 빌드·실행
├── Dockerfile
├── requirements.txt
└── .env                     # 환경 변수 (git 제외)
```

## 사전 요구 사항

- Docker
- Linux 호스트 (Synology NAS 등) — MDB SMB 동기화 시
- `vanpro97_call.mdb` 원본 (SMB 공유 또는 `data/` 직접 배치)

## 빠른 시작

### 1. 환경 변수 설정

프로젝트 루트에 `.env` 파일을 만듭니다.

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-secure-password
SECRET_KEY=your-random-secret-key
```

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `ADMIN_USERNAME` | 관리자 아이디 | `admin` |
| `ADMIN_PASSWORD` | 관리자 비밀번호 | (코드 내 fallback) |
| `SECRET_KEY` | JWT 서명 키 | (코드 내 fallback) |

선택적 변수 (Docker `deploy.sh` 또는 컨테이너 환경):

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `MDB_PATH` | 로컬 MDB 경로 | `/data/vanpro97_call.mdb` |
| `MDB_MOUNT_DIR` | SMB 마운트 경로 | `/mnt/vcallmanager1` |
| `MDB_META_PATH` | 동기화 메타 파일 | `/data/mdb_sync.meta` |
| `MDB_SYNC_STALE_MINUTES` | stale 판정 기준(분) | `10` |
| `INCOMING_TYPE_KEYWORDS` | 수신 통화 키워드(쉼표 구분) | `수신전화,수신` |

### 2. 배포

```bash
# MDB 없이도 컨테이너 기동 (동기화 후 사용)
./deploy.sh

# MDB 필수로 배포 (파일 없으면 실패)
./deploy.sh --require-mdb
```

배포 후 접속: **http://localhost:7002**

`deploy.sh`는 다음을 수행합니다.

- `vcall-web-service` 컨테이너 재생성
- `data/` → `/data`, SMB 마운트 → `/mnt/vcallmanager1` (읽기 전용) 볼륨 연결
- `app/` 소스를 볼륨으로 마운트해 UI 수정 시 재빌드 없이 반영

### 10분 주기 자동 동기화 (systemd)

```bash
sudo ./scripts/install-mdb-sync-timer.sh
sudo systemctl start vcall-mdb-sync.service   # 수동 1회 테스트
ls -la data/vanpro97_call.mdb
```

### 웹 UI에서 동기화

로그인 후 상단 **데이터 동기화** 버튼으로 즉시 동기화할 수 있습니다.  
동기화 상태(기준 시각, stale 여부, 마운트 가능 여부)도 함께 표시됩니다.

## API 개요

모든 API(로그인 제외)는 `Authorization: Bearer <token>` 헤더가 필요합니다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/api/auth/login` | 로그인 → JWT 발급 |
| `GET` | `/api/merchants?search=` | 가맹점 검색 |
| `GET` | `/api/history?saup_no=&tel_no=` | 가맹점 통화 이력 |
| `GET` | `/api/history/incoming?date=YYYY-MM-DD` | 수신 통화 목록 (KST) |
| `GET` | `/api/sync/status` | MDB 동기화 상태 |
| `POST` | `/api/sync/trigger` | MDB 동기화 실행 |

OpenAPI 문서: `http://localhost:7002/docs`

## 로컬 개발

Docker 없이 실행하려면 호스트에 `mdbtools`가 필요합니다.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export MDB_PATH=./data/vanpro97_call.mdb
uvicorn app.main:app --host 0.0.0.0 --port 7002 --reload
```

## MDB 테이블

| 테이블 | 용도 |
|--------|------|
| `TMER2` | 가맹점 마스터 (상호, 사업자번호, 전화, 대표자 등) |
| `TCALLCONTENT2` | 통화 내역 상세 |

스키마 참고: `data/vcall_table_TMER2_schema.csv`, `data/vcall_table_TCALLCONTENT2_schema.csv`

## 보안 참고

- `.env`는 저장소에 커밋하지 마세요 (`.gitignore`에 포함됨).
- 운영 환경에서는 `ADMIN_PASSWORD`, `SECRET_KEY`를 반드시 변경하세요.
- JWT 만료: 8시간 (`ACCESS_TOKEN_EXPIRE_HOURS`).
- MDB 파일 권한은 `640`, `data/` 디렉터리는 `750`으로 제한합니다.

## 라이선스

내부 운영용 프로젝트입니다. 별도 라이선스가 명시되지 않은 경우 조직 정책을 따릅니다.
