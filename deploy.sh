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

# 2-1. MDB·data 디렉토리 권한 최소화
echo "🔒 data 디렉토리 및 MDB 파일 권한을 최소화합니다..."
chmod 750 "$PROJECT_DIR/data"
[ -f "$PROJECT_DIR/data/vanpro97_call.mdb" ] && chmod 640 "$PROJECT_DIR/data/vanpro97_call.mdb"
[ -f "$PROJECT_DIR/data/mdb_sync.meta" ] && chmod 640 "$PROJECT_DIR/data/mdb_sync.meta"

# 2-2. 동기화·마운트·timer 설치 스크립트 실행 권한
chmod +x "$PROJECT_DIR/scripts/sync-mdb.sh" \
         "$PROJECT_DIR/scripts/mount-mdb-share.sh" \
         "$PROJECT_DIR/scripts/install-mdb-sync-timer.sh" 2>/dev/null || true

# 2-3. SMB 마운트 지점 (Synology: 공유 폴더 하위 경로 권장)
mkdir -p "$PROJECT_DIR/mnt/vcallmanager1"

# 3. 도커 이미지 빌드 (캐시 제거 모드로 클린 빌드)
echo "📦 수정한 코드로 도커 이미지를 새롭게 빌드합니다..."
docker build -t vcall-manager-web .

# 4. 리눅스 환경 볼륨 마운트 기준 도커 컨테이너 실행 (MDB 읽기 전용)
echo "🌐 7002번 포트로 서비스를 구동합니다 (컨테이너명: vcall-web-service)..."
docker run -d \
  --name vcall-web-service \
  -p 7002:7002 \
  --env-file "$PROJECT_DIR/.env" \
  -v "$PROJECT_DIR/data":/data:ro \
  -v "$PROJECT_DIR/app":/app \
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
