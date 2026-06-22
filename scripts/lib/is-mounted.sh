#!/bin/bash
# util-linux mountpoint 없는 환경(Synology NAS 등)용 마운트 확인

is_mounted() {
    local dir="${1%/}"
    if command -v mountpoint >/dev/null 2>&1; then
        mountpoint -q "$dir" 2>/dev/null
        return $?
    fi
    if command -v findmnt >/dev/null 2>&1; then
        findmnt -qn "$dir" >/dev/null 2>&1
        return $?
    fi
    awk -v target="$dir" '$2 == target { exit 0 } END { exit 1 }' /proc/mounts
}

# SMB/NFS 끊김 등으로 /proc/mounts 에는 있으나 접근 불가한 경로 걸러냄
is_accessible() {
    local dir="${1%/}"
    [ -d "$dir" ] && ls "$dir" >/dev/null 2>&1
}

has_mdb_in_mount() {
    local dir="${1%/}"
    is_accessible "$dir" || return 1
    [ -f "$dir/VANPRO97_call.mdb" ] || [ -f "$dir/vanpro97_call.mdb" ] || \
        find "$dir" -maxdepth 1 -iname 'vanpro97_call.mdb' -print -quit 2>/dev/null | grep -q .
}

# /proc/mounts 에 남아 있으나 원격 서버 재부팅 등으로 끊긴 CIFS 마운트
is_stale_mount() {
    local dir="${1%/}"
    if ! is_mounted "$dir"; then
        return 1
    fi
    if ! is_accessible "$dir"; then
        return 0
    fi
    if ! has_mdb_in_mount "$dir"; then
        return 0
    fi
    return 1
}

unmount_stale() {
    local dir="${1%/}"
    if ! is_mounted "$dir"; then
        return 0
    fi
    if ! is_stale_mount "$dir"; then
        return 0
    fi
    echo "[mount] stale SMB 마운트 해제: $dir" >&2
    sudo umount -l "$dir" 2>/dev/null || sudo umount "$dir" 2>/dev/null || true
}
