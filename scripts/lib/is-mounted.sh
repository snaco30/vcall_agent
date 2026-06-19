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
