#!/bin/bash

# 에러 발생 시 스크립트 중단
set -e

# 프로젝트 루트 디렉토리 정의 (현재 스크립트 위치 자동 인식)
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$PROJECT_DIR"

echo "=========================================="
echo "🚀 가맹점 관리 시스템 자동 배포를 시작합니다."
echo "=========================================="

# 1. 기존 가동 중인 컨테이너 확인 및 제거
if [ "$(docker ps -a -q -f name=vcall-web-service)" ]; then
    echo "🧹 기존 구동 중인 vcall-web-service 컨테이너를 중지하고 삭제합니다..."
    docker rm -f vcall-web-service
fi

# 2. 데이터 디렉토리 및 파일 유무 점검
if [ ! -d "$PROJECT_DIR/data" ] || [ ! -f "$PROJECT_DIR/data/vanpro97_call.mdb" ]; then
    echo "❌ [경고] $PROJECT_DIR/data/vanpro97_call.mdb 파일이 존재하지 않습니다."
    echo "👉 반드시 data 폴더를 만들고 mdb 파일을 넣은 후 다시 실행하세요."
    exit 1
fi

# 3. 도커 이미지 빌드 (캐시 제거 모드로 클린 빌드)
echo "📦 수정한 코드로 도ker 이미지를 새롭게 빌드합니다..."
docker build --no-cache -t vcall-manager-web .

# 4. 리눅스 환경 볼륨 마운트 기준 도커 컨테이너 실행
echo "🌐 7000번 포트로 서비스를 구동합니다 (컨테이너명: vcall-web-service)..."
docker run -d \
  --name vcall-web-service \
  -p 7000:7000 \
  -v "$PROJECT_DIR/data":/data \
  --restart always \
  vcall-manager-web

echo "=========================================="
echo "✅ 배포가 성공적으로 완료되었습니다!"
echo "👉 접속 주소: http://localhost:7000"
echo "=========================================="