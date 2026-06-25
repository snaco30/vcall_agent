#!/bin/bash
# Synology 등 systemd timer가 어려운 환경: 매일 09:00 cron 등록
# 사용: sudo ./scripts/install-mdb-sync-daily-cron.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DAILY_SCRIPT="$PROJECT_DIR/scripts/run-mdb-sync-daily.sh"
CRON_MARK="# vcall-mdb-sync-daily"
CRON_LINE="0 9 * * * ${DAILY_SCRIPT}"

if [ "$(id -u)" -ne 0 ]; then
    echo "❌ root 권한이 필요합니다: sudo $0" >&2
    exit 1
fi

chmod +x "$DAILY_SCRIPT" "$PROJECT_DIR/scripts/sync-mdb.sh"

SVC_USER="${SVC_USER:-${SUDO_USER:-$(stat -c '%U' "$PROJECT_DIR")}}"

if command -v crontab >/dev/null 2>&1; then
    EXISTING="$(crontab -u "$SVC_USER" -l 2>/dev/null || true)"
    if echo "$EXISTING" | grep -Fq "$CRON_MARK"; then
        EXISTING="$(echo "$EXISTING" | grep -Fv "$CRON_MARK" | grep -Fv "$DAILY_SCRIPT" || true)"
    fi
    {
        echo "$EXISTING" | sed '/^$/d'
        echo "$CRON_LINE $CRON_MARK"
    } | crontab -u "$SVC_USER" -
    echo "✅ cron 등록 완료 (사용자: $SVC_USER, 매일 09:00)"
    echo "   $CRON_LINE"
    crontab -u "$SVC_USER" -l | grep vcall-mdb || true
    exit 0
fi

echo "⚠️  crontab 명령이 없습니다. DSM 작업 스케줄러에 수동 등록하세요:"
echo ""
echo "   사용자 지정 스크립트: $DAILY_SCRIPT"
echo "   일정: 매일 09:00"
echo "   로그: $PROJECT_DIR/data/mdb-sync.log"
echo ""
echo "   또는 /etc/cron.d/ 에 다음 한 줄 추가:"
echo "   0 9 * * * $SVC_USER $DAILY_SCRIPT $CRON_MARK"
