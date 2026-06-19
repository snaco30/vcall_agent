#!/bin/bash
# Synology NAS 등 호스트에서 SMB 원격 공유 마운트 (1회 또는 부팅 스크립트용)
# 사용 예:
#   MDB_SMB_USER=myuser MDB_SMB_PASS=secret ./scripts/mount-mdb-share.sh
#   ./scripts/mount-mdb-share.sh --check

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=lib/is-mounted.sh
source "$SCRIPT_DIR/lib/is-mounted.sh"

SMB_SERVER="${MDB_SMB_SERVER:-posbankserver}"
SMB_SHARE="${MDB_SMB_SHARE:-vcallmanager1}"
MOUNT_DIR="${MDB_MOUNT_DIR:-$PROJECT_DIR/mnt/vcallmanager1}"
SMB_USER="${MDB_SMB_USER:-}"
SMB_PASS="${MDB_SMB_PASS:-}"
SMB_VERS="${MDB_SMB_VERS:-3.0}"

usage() {
    cat <<EOF
SMB MDB 공유 마운트

환경변수:
  MDB_SMB_SERVER  원격 서버 (기본: posbankserver)
  MDB_SMB_SHARE   공유 이름 (기본: vcallmanager1)
  MDB_MOUNT_DIR   로컬 마운트 경로 (기본: \$PROJECT_DIR/mnt/vcallmanager1)
  MDB_SMB_USER    SMB 계정 (필수, --check 제외)
  MDB_SMB_PASS    SMB 비밀번호 (필수, --check 제외)
  MDB_SMB_VERS    SMB 버전 (기본: 3.0, Synology 권장)

옵션:
  --check   마운트 상태만 확인
  --help    이 도움말

DSM GUI 대안: File Station → 도구 → 원격 폴더 마운트 → CIFS
  폴더: \\\\${SMB_SERVER}\\${SMB_SHARE}
  위치: ${MOUNT_DIR}
  「시작 시 자동으로 마운트」 체크
EOF
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
    usage
    exit 0
fi

if [ "${1:-}" = "--check" ]; then
    if is_mounted "$MOUNT_DIR"; then
        echo "✅ 마운트됨: $MOUNT_DIR"
        ls -la "$MOUNT_DIR" 2>/dev/null | head -20
        exit 0
    fi
    echo "❌ 마운트 안 됨: $MOUNT_DIR"
    exit 1
fi

if [ -z "$SMB_USER" ] || [ -z "$SMB_PASS" ]; then
    echo "❌ MDB_SMB_USER, MDB_SMB_PASS 환경변수가 필요합니다." >&2
    echo "   또는 DSM File Station에서 GUI로 마운트하세요." >&2
    usage >&2
    exit 1
fi

RUN_USER="$(id -un)"
RUN_GID="$(id -g)"

mkdir -p "$MOUNT_DIR"

if is_mounted "$MOUNT_DIR"; then
    echo "✅ 이미 마운트됨: $MOUNT_DIR"
    exit 0
fi

REMOTE="//${SMB_SERVER}/${SMB_SHARE}"
OPTS="username=${SMB_USER},password=${SMB_PASS},uid=${RUN_USER},gid=${RUN_GID},iocharset=utf8,vers=${SMB_VERS}"

echo "📂 마운트: $REMOTE → $MOUNT_DIR"
sudo mount -t cifs "$REMOTE" "$MOUNT_DIR" -o "$OPTS"

if is_mounted "$MOUNT_DIR"; then
    echo "✅ 마운트 완료"
    ls -la "$MOUNT_DIR" | head -20
else
    echo "❌ 마운트 실패" >&2
    exit 1
fi
