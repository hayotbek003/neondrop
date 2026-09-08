#!/usr/bin/env bash
# Exit immediately if a command exits with a non-zero status
set -o errexit

echo "====================================================="
echo "  NEONDROP PRODUCTION STARTUP"
echo "====================================================="

# Step 0: Inspect active database engine & persistence status
echo "==> Verifying database engine and persistence configuration..."
python manage.py check_database_config

# Run database migrations before launching web server
echo "==> Running Django database migrations..."
python manage.py migrate --noinput

# Ensure persistent catalog and zero data loss on fresh PostgreSQL connections
echo "==> Verifying case catalog persistence..."
python manage.py ensure_persistent_data

# Verify system integrity
echo "==> Verifying system integrity..."
python manage.py check

# Step 1: Promote Smoke to staff/superuser — password is NEVER changed.
# Smoke's original password from the database backup is preserved as-is.
echo "==> Ensuring Smoke admin permissions (password unchanged)..."
python manage.py promote_admin Smoke

# Step 2: Create or update the 'admin' superuser using ADMIN_PASSWORD env var.
# Set ADMIN_PASSWORD in Render Dashboard -> Environment Variables.
# This does NOT affect Smoke's password in any way.
echo "==> Ensuring admin superuser (via ADMIN_PASSWORD env var)..."
python manage.py promote_admin admin --update-existing


# Start Gunicorn server
PORT="${PORT:-8000}"
WORKERS="${GUNICORN_WORKERS:-2}"
THREADS="${GUNICORN_THREADS:-2}"
TIMEOUT="${GUNICORN_TIMEOUT:-120}"

echo "==> Starting Gunicorn on port ${PORT} (workers=${WORKERS}, threads=${THREADS})..."
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:${PORT} \
    --workers ${WORKERS} \
    --threads ${THREADS} \
    --timeout ${TIMEOUT} \
    --access-logfile - \
    --error-logfile -
