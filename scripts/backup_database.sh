#!/usr/bin/env bash
# ==============================================================================
# NEONDROP - Database Backup Script (Linux / macOS / Render / Docker)
# ==============================================================================
set -e

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="backups/database"
mkdir -p "$BACKUP_DIR"

echo "========================================================"
echo " [NEONDROP] Starting Automated Database Backup..."
echo " Timestamp: $TIMESTAMP"
echo "========================================================"

# Check if PostgreSQL DATABASE_URL is set and pg_dump is available
if [ -n "$DATABASE_URL" ] && [[ "$DATABASE_URL" == postgres* ]] && command -v pg_dump >/dev/null 2>&1; then
    PG_DUMP_FILE="$BACKUP_DIR/neondrop_pgdump_${TIMESTAMP}.dump"
    echo " -> Creating native PostgreSQL dump: $PG_DUMP_FILE"
    pg_dump "$DATABASE_URL" -Fc -f "$PG_DUMP_FILE"
    echo " -> Native PostgreSQL dump completed: $PG_DUMP_FILE"
fi

# Run Django JSON backup
echo " -> Running Django zero-data-loss JSON export..."
python manage.py backup_data --output "$BACKUP_DIR/neondrop_db_${TIMESTAMP}.json"

echo "========================================================"
echo " [SUCCESS] Database Backup Completed Successfully!"
echo " Location: $BACKUP_DIR"
echo "========================================================"
