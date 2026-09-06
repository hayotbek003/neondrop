#!/usr/bin/env bash
# ==============================================================================
# NEONDROP - Media Assets Backup Script (Linux / macOS / Render / Docker)
# ==============================================================================
set -e

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="backups/media"
mkdir -p "$BACKUP_DIR"

echo "========================================================"
echo " [NEONDROP] Starting Media Backup..."
echo " Timestamp: $TIMESTAMP"
echo "========================================================"

python manage.py backup_media --output "$BACKUP_DIR/neondrop_media_${TIMESTAMP}.tar.gz"

echo "========================================================"
echo " [SUCCESS] Media Backup Completed Successfully!"
echo " Location: $BACKUP_DIR"
echo "========================================================"
