#!/usr/bin/env bash
# ==============================================================================
# NEONDROP - Database Restore Script (Linux / macOS / Render / Docker)
# ==============================================================================
set -e

BACKUP_FILE="$1"

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: ./scripts/restore_database.sh <path_to_backup.json>"
    echo "Example: ./scripts/restore_database.sh backups/database/neondrop_db_20260906_120000.json"
    exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
    echo "Error: Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo "========================================================"
echo " [NEONDROP] Restoring Database from: $BACKUP_FILE"
echo "========================================================"

python manage.py restore_data "$BACKUP_FILE" --clean
python manage.py verify_migration --compare "$BACKUP_FILE"

echo "========================================================"
echo " [SUCCESS] Database Restored and Verified with 0 Data Loss!"
echo "========================================================"
