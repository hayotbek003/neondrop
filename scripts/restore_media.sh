#!/usr/bin/env bash
# ==============================================================================
# NEONDROP - Media Assets Restore Script (Linux / macOS / Render / Docker)
# ==============================================================================
set -e

ARCHIVE_FILE="$1"

if [ -z "$ARCHIVE_FILE" ]; then
    echo "Usage: ./scripts/restore_media.sh <path_to_media_archive.tar.gz>"
    echo "Example: ./scripts/restore_media.sh backups/media/neondrop_media_20260906_120000.tar.gz"
    exit 1
fi

if [ ! -f "$ARCHIVE_FILE" ]; then
    echo "Error: Media archive file not found: $ARCHIVE_FILE"
    exit 1
fi

echo "========================================================"
echo " [NEONDROP] Restoring Media Assets from: $ARCHIVE_FILE"
echo "========================================================"

python manage.py restore_media "$ARCHIVE_FILE"

echo "========================================================"
echo " [SUCCESS] Media Assets Restored Successfully!"
echo "========================================================"
