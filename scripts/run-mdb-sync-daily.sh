#!/bin/bash
# 매일 오전 9시 실행: SMB 연결 확인·stale 복구 후 MDB 로컬 복사
# systemd timer 또는 DSM 작업 스케줄러·cron에서 호출

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG="${MDB_SYNC_LOG:-$PROJECT_DIR/data/mdb-sync.log}"

mkdir -p "$(dirname "$LOG")" 2>/dev/null || true

{
    echo "======== $(date -Iseconds) daily mdb sync start ========"
    if [ -f "$PROJECT_DIR/.mdb-smb.env" ]; then
        # shellcheck disable=SC1091
        set -a
        source "$PROJECT_DIR/.mdb-smb.env"
        set +a
    fi
    "$SCRIPT_DIR/sync-mdb.sh"
    echo "======== $(date -Iseconds) daily mdb sync end ========"
} >>"$LOG" 2>&1
