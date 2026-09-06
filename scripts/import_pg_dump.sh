#!/usr/bin/env bash
# ==============================================================================
# NEONDROP - Native PostgreSQL Restore Script
# ==============================================================================
set -e

DUMP_FILE="$1"

if [ -z "$DUMP_FILE" ]; then
    echo "Usage: ./scripts/import_pg_dump.sh <path_to_pg_dump.dump>"
    exit 1
fi

if [ -z "$DATABASE_URL" ]; then
    echo "Error: DATABASE_URL environment variable is not set."
    exit 1
fi

if [ ! -f "$DUMP_FILE" ]; then
    echo "Error: Dump file not found: $DUMP_FILE"
    exit 1
fi

echo "========================================================"
echo " [NEONDROP] Restoring Native PostgreSQL Dump to DATABASE_URL..."
echo " File: $DUMP_FILE"
echo "========================================================"

pg_restore --clean --if-exists --no-owner --no-privileges -d "$DATABASE_URL" -v "$DUMP_FILE"

echo "========================================================"
echo " [SUCCESS] PostgreSQL Restore Complete!"
echo " Running verification audit..."
echo "========================================================"

python manage.py verify_migration
