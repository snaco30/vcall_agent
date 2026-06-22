#!/bin/bash
# SMB 공유 MDB → 로컬 복사본 동기화 (10분 주기 systemd timer용)
# 실패 시 기존 복사본 유지 (posbankserver 꺼짐 등)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=lib/is-mounted.sh
source "$SCRIPT_DIR/lib/is-mounted.sh"
# shellcheck source=lib/mount-paths.sh
source "$SCRIPT_DIR/lib/mount-paths.sh"

# 선택: 자동 재마운트용 SMB 계정 (.mdb-smb.env, git 제외)
if [ -f "$PROJECT_DIR/.mdb-smb.env" ]; then
    # shellcheck disable=SC1091
    set -a
    source "$PROJECT_DIR/.mdb-smb.env"
    set +a
fi

MOUNT_DIR="${MDB_MOUNT_DIR:-$(default_mount_dir)}"
ALT_MOUNT_DIR="$(legacy_mount_dir)"
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

file_mtime_iso() {
    local file="$1"
    if date -r "$file" -Iseconds >/dev/null 2>&1; then
        date -r "$file" -Iseconds
    elif stat -c '%Y' "$file" >/dev/null 2>&1; then
        date -d "@$(stat -c '%Y' "$file")" -Iseconds
    else
        date -Iseconds
    fi
}

# SMB 미연결 등으로 동기화 못 했을 때, 기존 복사본 mtime으로 meta 부트스트랩
ensure_local_copy_meta() {
    if [ ! -f "$DST" ] || [ -f "$META" ]; then
        return 0
    fi
    local synced_at
    synced_at="$(file_mtime_iso "$DST")"
    printf '{"synced_at":"%s","source":"local_copy"}\n' "$synced_at" > "$META_TMP"
    chmod 640 "$META_TMP"
    mv -f "$META_TMP" "$META"
    log "로컬 복사본 meta 생성 ($synced_at)"
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

has_mdb_in_dir() {
    has_mdb_in_mount "$1"
}

recover_mount_if_stale() {
    local dir="$1"
    if ! is_stale_mount "$dir"; then
        return 0
    fi
    log "stale SMB 마운트 감지 ($dir) — 해제 후 재마운트 시도"
    unmount_stale "$dir"
    if [ -n "${MDB_SMB_USER:-}" ] && [ -n "${MDB_SMB_PASS:-}" ]; then
        MDB_MOUNT_DIR="$dir" "$SCRIPT_DIR/mount-mdb-share.sh" || true
    else
        log "SMB 계정 없음 — DSM/File Station에서 재마운트하거나 .mdb-smb.env 설정"
    fi
}

# 구형 mnt/vcallmanager1 에만 MDB가 있는 경우 자동 인식
if [ -z "${MDB_MOUNT_DIR:-}" ] && ! has_mdb_in_dir "$MOUNT_DIR" && has_mdb_in_dir "$ALT_MOUNT_DIR"; then
    log "MDB가 mnt/vcallmanager1 에 있음 — 해당 경로 사용"
    MOUNT_DIR="$ALT_MOUNT_DIR"
fi

recover_mount_if_stale "$MOUNT_DIR"
if [ "$MOUNT_DIR" != "$ALT_MOUNT_DIR" ]; then
    recover_mount_if_stale "$ALT_MOUNT_DIR"
fi

# 마운트·소스 없음 → 기존 복사본 유지
if ! is_mounted "$MOUNT_DIR" || ! is_accessible "$MOUNT_DIR"; then
    if is_mounted "$MOUNT_DIR" && ! is_accessible "$MOUNT_DIR"; then
        log "SMB 마운트 끊김 ($MOUNT_DIR) — 기존 복사본 유지"
    else
        log "SMB 마운트 없음 ($MOUNT_DIR) — 기존 복사본 유지"
    fi
    ensure_local_copy_meta
    exit 0
fi

SRC="$(resolve_src)"
if [ -z "$SRC" ] || [ ! -f "$SRC" ]; then
    log "소스 MDB 없음 — 기존 복사본 유지"
    ensure_local_copy_meta
    exit 0
fi

mkdir -p "$DATA_DIR"
chmod 750 "$DATA_DIR" 2>/dev/null || true

if ! cp -f "$SRC" "$TMP"; then
    log "복사 실패 — 기존 복사본 유지"
    rm -f "$TMP"
    exit 0
fi

if command -v mdb-tables >/dev/null 2>&1; then
    if ! mdb-tables "$TMP" >/dev/null 2>&1; then
        log "mdb 무결성 검증 실패 — 기존 복사본 유지"
        rm -f "$TMP"
        exit 0
    fi
else
    log "mdb-tables 없음 — 무결성 검증 생략 (Entware: opkg install mdbtools)"
fi

chmod 640 "$TMP"
mv -f "$TMP" "$DST"

SYNCED_AT="$(date -Iseconds)"
printf '{"synced_at":"%s","source":"%s"}\n' "$SYNCED_AT" "$SRC" > "$META_TMP"
chmod 640 "$META_TMP"
mv -f "$META_TMP" "$META"

log "동기화 완료: $SRC → $DST ($SYNCED_AT)"
