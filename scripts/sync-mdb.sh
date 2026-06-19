#!/bin/bash
# SMB 공유 MDB → 로컬 복사본 동기화 (10분 주기 systemd timer용)
# 실패 시 기존 복사본 유지 (posbankserver 꺼짐 등)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

MOUNT_DIR="${MDB_MOUNT_DIR:-/mnt/vcallmanager1}"
DATA_DIR="${MDB_DATA_DIR:-$PROJECT_DIR/data}"
DST="${MDB_DST:-$DATA_DIR/vanpro97_call.mdb}"
META="${MDB_META:-$DATA_DIR/mdb_sync.meta}"
TMP="${DST}.tmp"
META_TMP="${META}.tmp"

CANDIDATES=(
    "VANPRO97_call.mdb"
    "vanpro97_call.mdb"
    "VANPRO97_CALL.MDB"
)

log() {
    echo "[sync-mdb] $(date -Iseconds) $*"
}

resolve_src() {
    local name path
    for name in "${CANDIDATES[@]}"; do
        path="$MOUNT_DIR/$name"
        if [ -f "$path" ]; then
            echo "$path"
            return 0
        fi
    done
    find "$MOUNT_DIR" -maxdepth 1 -iname 'vanpro97_call.mdb' -print -quit 2>/dev/null || true
}

# 마운트·소스 없음 → 기존 복사본 유지
if ! mountpoint -q "$MOUNT_DIR" 2>/dev/null; then
    log "SMB 마운트 없음 ($MOUNT_DIR) — 기존 복사본 유지"
    exit 0
fi

SRC="$(resolve_src)"
if [ -z "$SRC" ] || [ ! -f "$SRC" ]; then
    log "소스 MDB 없음 — 기존 복사본 유지"
    exit 0
fi

mkdir -p "$DATA_DIR"
chmod 750 "$DATA_DIR" 2>/dev/null || true

if ! cp -f "$SRC" "$TMP"; then
    log "복사 실패 — 기존 복사본 유지"
    rm -f "$TMP"
    exit 0
fi

if ! mdb-tables "$TMP" >/dev/null 2>&1; then
    log "mdb 무결성 검증 실패 — 기존 복사본 유지"
    rm -f "$TMP"
    exit 0
fi

chmod 640 "$TMP"
mv -f "$TMP" "$DST"

SYNCED_AT="$(date -Iseconds)"
printf '{"synced_at":"%s","source":"%s"}\n' "$SYNCED_AT" "$SRC" > "$META_TMP"
chmod 640 "$META_TMP"
mv -f "$META_TMP" "$META"

log "동기화 완료: $SRC → $DST ($SYNCED_AT)"
