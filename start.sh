#!/usr/bin/env bash
# Exit immediately if a command exits with a non-zero status
set -o errexit

echo "====================================================="
echo "  NEONDROP PRODUCTION STARTUP"
echo "====================================================="

# Run database migrations before launching web server
echo "==> Running Django database migrations..."
python manage.py migrate --noinput


# Verify system integrity
echo "==> Verifying system integrity..."
python manage.py check

# Ensure administrator accounts exist with staff and superuser permissions.
# ADMIN_PASSWORD must be set in Render Dashboard -> Environment Variables.
# It is NEVER stored in source code or Git.
echo "==> Ensuring administrator accounts..."
python manage.py promote_admin admin Smoke --update-existing


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
