#!/usr/bin/env bash
# ==============================================================================
# NEONDROP - Native PostgreSQL Dump Script
# ==============================================================================
set -e

if [ -z "$DATABASE_URL" ]; then
    echo "Error: DATABASE_URL environment variable is not set."
    echo "Example: export DATABASE_URL=postgresql://user:password@host:port/dbname"
    exit 1
fi

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="backups/database"
mkdir -p "$BACKUP_DIR"
OUTPUT_FILE="$BACKUP_DIR/neondrop_pg_${TIMESTAMP}.dump"

echo "========================================================"
echo " [NEONDROP] Exporting Native PostgreSQL Dump..."
echo " Output: $OUTPUT_FILE"
echo "========================================================"

pg_dump "$DATABASE_URL" -Fc -v -f "$OUTPUT_FILE"

echo "========================================================"
echo " [SUCCESS] PostgreSQL Dump Created: $OUTPUT_FILE"
echo " Size: $(du -h "$OUTPUT_FILE" | cut -f1)"
echo "========================================================"
