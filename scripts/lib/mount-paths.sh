#!/bin/bash
# SMB 마운트 경로 기본값 (PROJECT_DIR 설정 후 source)

DEFAULT_MOUNT_SUBPATH="mnt/vcallmanager1"
LEGACY_MOUNT_SUBPATH="data/mnt/vcallmanager1"
CONTAINER_DEFAULT_MOUNT_DIR="/mnt/vcallmanager1"

default_mount_dir() {
    echo "${PROJECT_DIR}/${DEFAULT_MOUNT_SUBPATH}"
}

legacy_mount_dir() {
    echo "${PROJECT_DIR}/${LEGACY_MOUNT_SUBPATH}"
}

container_mount_dir_for() {
    echo "$CONTAINER_DEFAULT_MOUNT_DIR"
}
