#!/bin/bash

# 에러 발생 시 스크립트 중단
set -e

# 프로젝트 루트 디렉토리 정의 (현재 스크립트 위치 자동 인식)
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$PROJECT_DIR"

REQUIRE_MDB=false
for arg in "$@"; do
    if [ "$arg" = "--require-mdb" ]; then
        REQUIRE_MDB=true
    fi
done

echo "=========================================="
echo "🚀 가맹점 관리 시스템 자동 배포를 시작합니다."
echo "=========================================="

# 1. 기존 가동 중인 컨테이너 확인 및 제거
if [ "$(docker ps -a -q -f name=vcall-web-service)" ]; then
    echo "🧹 기존 구동 중인 vcall-web-service 컨테이너를 중지하고 삭제합니다..."
    docker rm -f vcall-web-service
fi

# 2. 데이터 디렉토리 준비
mkdir -p "$PROJECT_DIR/data"

# 2-1. 동기화·마운트·timer 설치 스크립트 실행 권한
chmod +x "$PROJECT_DIR/scripts/sync-mdb.sh" \
         "$PROJECT_DIR/scripts/mount-mdb-share.sh" \
         "$PROJECT_DIR/scripts/install-mdb-sync-timer.sh" 2>/dev/null || true

# 2-2. MDB 동기화 (마운트 없으면 기존 복사본 유지)
echo "🔄 MDB 동기화 시도 (마운트 없으면 기존 복사본 유지)..."
"$PROJECT_DIR/scripts/sync-mdb.sh" || true

if [ ! -f "$PROJECT_DIR/data/vanpro97_call.mdb" ]; then
    if [ "$REQUIRE_MDB" = true ]; then
        echo "❌ [경고] $PROJECT_DIR/data/vanpro97_call.mdb 파일이 존재하지 않습니다."
        echo "👉 data 폴더에 mdb 파일을 넣거나 scripts/sync-mdb.sh 로 동기화한 후 다시 실행하세요."
        exit 1
    fi
    echo "⚠️  로컬 MDB 복사본이 없습니다. SMB 동기화 또는 수동 복사 후 서비스가 가능합니다."
else
    echo "✅ 로컬 MDB 복사본 확인됨."
fi

# 2-3. MDB·data 디렉토리 권한 최소화
echo "🔒 data 디렉토리 및 MDB 파일 권한을 최소화합니다..."
chmod 750 "$PROJECT_DIR/data"
[ -f "$PROJECT_DIR/data/vanpro97_call.mdb" ] && chmod 640 "$PROJECT_DIR/data/vanpro97_call.mdb"
[ -f "$PROJECT_DIR/data/mdb_sync.meta" ] && chmod 640 "$PROJECT_DIR/data/mdb_sync.meta"

# 2-4. SMB 마운트 지점 (Synology: 공유 폴더 하위 경로 권장)
# 기본: $PROJECT_DIR/mnt/vcallmanager1
# DSM에서 data/mnt 아래에 마운트한 경우 자동 인식
# shellcheck source=scripts/lib/is-mounted.sh
source "$PROJECT_DIR/scripts/lib/is-mounted.sh"

MOUNT_HOST="$PROJECT_DIR/mnt/vcallmanager1"
ALT_MOUNT_HOST="$PROJECT_DIR/data/mnt/vcallmanager1"
mkdir -p "$MOUNT_HOST"
has_mdb() {
    local dir="$1"
    is_accessible "$dir" || return 1
    [ -f "$dir/VANPRO97_call.mdb" ] || [ -f "$dir/vanpro97_call.mdb" ] || \
        find "$dir" -maxdepth 1 -iname 'vanpro97_call.mdb' -print -quit 2>/dev/null | grep -q .
}
if ! has_mdb "$MOUNT_HOST" && has_mdb "$ALT_MOUNT_HOST"; then
    echo "⚠️  MDB가 data/mnt/vcallmanager1 에 있습니다. Docker 볼륨을 해당 경로로 연결합니다."
    echo "   (권장: DSM 마운트 위치를 $MOUNT_HOST 로 옮기면 구조가 단순해집니다.)"
    MOUNT_HOST="$ALT_MOUNT_HOST"
elif ! is_accessible "$MOUNT_HOST" && ! is_accessible "$ALT_MOUNT_HOST"; then
    echo "⚠️  SMB 마운트 경로에 접근할 수 없습니다 (서버 다운 또는 끊김). 로컬 MDB 복사본으로 서비스합니다."
fi

# 3. 도커 이미지 빌드 (캐시 제거 모드로 클린 빌드)
echo "📦 수정한 코드로 도커 이미지를 새롭게 빌드합니다..."
docker build -t vcall-manager-web .

# 4. 리눅스 환경 볼륨 마운트 기준 도커 컨테이너 실행 (MDB 읽기 전용)
echo "🌐 7002번 포트로 서비스를 구동합니다 (컨테이너명: vcall-web-service)..."
DOCKER_VOLUMES=(
  -v "$PROJECT_DIR/data":/data
  -v "$PROJECT_DIR/app":/app
)
if is_accessible "$MOUNT_HOST"; then
    DOCKER_VOLUMES+=(-v "$MOUNT_HOST":/mnt/vcallmanager1:ro)
else
    echo "⚠️  SMB 볼륨 마운트 생략 ($MOUNT_HOST 접근 불가)"
fi

docker run -d \
  --name vcall-web-service \
  -p 7002:7002 \
  --env-file "$PROJECT_DIR/.env" \
  -e MDB_MOUNT_DIR=/mnt/vcallmanager1 \
  "${DOCKER_VOLUMES[@]}" \
  --restart always \
  vcall-manager-web

echo "=========================================="
echo "✅ 배포가 성공적으로 완료되었습니다!"
echo "👉 접속 주소: http://localhost:7002"
echo ""
echo "📋 MDB 10분 주기 동기화 (호스트에서 1회 설정):"
echo ""
echo "   1) SMB 마운트 (DSM File Station 권장, 또는 SSH):"
echo "      mkdir -p $PROJECT_DIR/mnt/vcallmanager1"
echo "      # File Station → 도구 → 원격 폴더 마운트 → CIFS"
echo "      #   \\\\posbankserver\\vcallmanager1 → $PROJECT_DIR/mnt/vcallmanager1"
echo "      # (data/mnt/vcallmanager1 에 마운트한 경우 deploy.sh 가 자동 인식)"
echo "      # 또는:"
echo "      MDB_SMB_USER=계정 MDB_SMB_PASS=비밀번호 $PROJECT_DIR/scripts/mount-mdb-share.sh"
echo "      $PROJECT_DIR/scripts/mount-mdb-share.sh --check"
echo ""
echo "   2) systemd timer 설치 (구형 DSM: enable --now 미지원):"
echo "      sudo $PROJECT_DIR/scripts/install-mdb-sync-timer.sh"
echo ""
echo "   3) 동기화 테스트:"
echo "      sudo systemctl start vcall-mdb-sync.service"
echo "      ls -la $PROJECT_DIR/data/vanpro97_call.mdb"
echo "=========================================="
