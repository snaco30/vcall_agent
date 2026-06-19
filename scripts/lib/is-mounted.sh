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
