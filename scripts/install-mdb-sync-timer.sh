#!/bin/bash
# systemd timer 설치 (PROJECT_DIR·실행 사용자 자동 반영, 구형 systemd 호환)
# 사용: sudo ./scripts/install-mdb-sync-timer.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=lib/mount-paths.sh
source "$SCRIPT_DIR/lib/mount-paths.sh"

if [ "$(id -u)" -ne 0 ]; then
    echo "❌ root 권한이 필요합니다: sudo $0" >&2
    exit 1
fi

# deploy를 실행한 사용자 추정 (sudo 호출 시 SUDO_USER, 아니면 소유자)
SVC_USER="${SVC_USER:-${SUDO_USER:-$(stat -c '%U' "$PROJECT_DIR")}}"
MOUNT_DIR="${MDB_MOUNT_DIR:-$(default_mount_dir)}"
DATA_DIR="${MDB_DATA_DIR:-$PROJECT_DIR/data}"
SYNC_SCRIPT="$PROJECT_DIR/scripts/sync-mdb.sh"
DAILY_SCRIPT="$PROJECT_DIR/scripts/run-mdb-sync-daily.sh"
SYSTEMD_DIR="/etc/systemd/system"

if [ ! -x "$SYNC_SCRIPT" ]; then
    chmod +x "$SYNC_SCRIPT"
fi
if [ ! -x "$DAILY_SCRIPT" ]; then
    chmod +x "$DAILY_SCRIPT"
fi

mkdir -p "$MOUNT_DIR"

ENV_FILE_LINE=""
if [ -f "$PROJECT_DIR/.mdb-smb.env" ]; then
    ENV_FILE_LINE="EnvironmentFile=-${PROJECT_DIR}/.mdb-smb.env"
fi

cat > "$SYSTEMD_DIR/vcall-mdb-sync.service" <<EOF
[Unit]
Description=V-CALL MDB sync from SMB share
After=network-online.target remote-fs.target
Wants=network-online.target

[Service]
Type=oneshot
User=${SVC_USER}
${ENV_FILE_LINE}
Environment=MDB_MOUNT_DIR=${MOUNT_DIR}
Environment=MDB_DATA_DIR=${DATA_DIR}
ExecStart=${SYNC_SCRIPT}
EOF

cat > "$SYSTEMD_DIR/vcall-mdb-sync-daily.service" <<EOF
[Unit]
Description=V-CALL MDB daily sync at 09:00 (SMB check + copy)
After=network-online.target remote-fs.target
Wants=network-online.target

[Service]
Type=oneshot
User=${SVC_USER}
${ENV_FILE_LINE}
Environment=MDB_MOUNT_DIR=${MOUNT_DIR}
Environment=MDB_DATA_DIR=${DATA_DIR}
ExecStart=${DAILY_SCRIPT}
EOF

cp "$SCRIPT_DIR/systemd/vcall-mdb-sync.timer" "$SYSTEMD_DIR/vcall-mdb-sync.timer"
cp "$SCRIPT_DIR/systemd/vcall-mdb-sync-daily.timer" "$SYSTEMD_DIR/vcall-mdb-sync-daily.timer"

systemctl daemon-reload
systemctl enable vcall-mdb-sync.timer
systemctl enable vcall-mdb-sync-daily.timer
systemctl start vcall-mdb-sync.timer
systemctl start vcall-mdb-sync-daily.timer

echo "=========================================="
echo "✅ vcall-mdb-sync.timer 설치 완료"
echo "   · 10분 주기: vcall-mdb-sync.timer"
echo "   · 매일 09:00: vcall-mdb-sync-daily.timer"
echo "   User:         $SVC_USER"
echo "   Mount dir:    $MOUNT_DIR"
echo "   Data dir:     $DATA_DIR"
echo "   Daily log:    $DATA_DIR/mdb-sync.log"
echo ""
echo "📋 확인 명령:"
echo "   systemctl list-timers vcall-mdb-sync*"
echo "   systemctl status vcall-mdb-sync-daily.timer"
echo "   sudo systemctl start vcall-mdb-sync-daily.service"
echo "   sudo journalctl -u vcall-mdb-sync-daily.service -n 20 --no-pager"
echo "   tail -30 $DATA_DIR/mdb-sync.log"
echo "   ls -la $DATA_DIR/vanpro97_call.mdb"
echo ""
echo "   Synology에서 timer 미동작 시:"
echo "   sudo $PROJECT_DIR/scripts/install-mdb-sync-daily-cron.sh"
echo "=========================================="
