#!/usr/bin/env bash
# Exit immediately if a command exits with a non-zero status
set -o errexit

echo "====================================================="
echo "  NEONDROP PRODUCTION STARTUP"
echo "====================================================="

# Guard: Strictly enforce PostgreSQL connection on Render production
if [ -n "$RENDER" ] || [ -n "$RENDER_SERVICE_ID" ]; then
    # Clear placeholder values if accidentally pasted
    case "$DATABASE_URL" in
        *dpg-xxx*|*:PASSWORD@*|*xxx*)
            DATABASE_URL=""
            ;;
    esac

    if [ -z "$DATABASE_URL" ] && [ -z "$INTERNAL_DATABASE_URL" ] && [ -z "$POSTGRES_URL" ] && [ -z "$DATABASE_PRIVATE_URL" ] && [ -z "$DB_URL" ]; then
        echo ""
        echo "======================================================================"
        echo "  [FATAL ERROR] DATABASE_URL IS NOT CONFIGURED IN RENDER PRODUCTION!"
        echo "======================================================================"
        echo "  NEONDROP production is strictly prohibited from running on SQLite."
        echo "  Running on SQLite causes all data to be wiped on 15-minute spin-down."
        echo ""
        echo "  ACTION REQUIRED IN RENDER DASHBOARD:"
        echo "  1. Open https://dashboard.render.com/"
        echo "  2. Click on your PostgreSQL database: 'neondrop-db'"
        echo "  3. Under 'Connections', copy the real 'Internal Database URL'"
        echo "  4. Click on Web Service: 'neondrop-ujly' -> 'Environment'"
        echo "  5. Add/Update Environment Variable:"
        echo "     Key:   DATABASE_URL"
        echo "     Value: <paste your actual copied Internal Database URL>"
        echo "  6. Click 'Save Changes' to deploy with persistent PostgreSQL."
        echo "======================================================================"
        echo ""
        exit 1
    fi
fi

# Step 0: Inspect active database engine & persistence status
echo "==> Verifying database engine and persistence configuration..."
python manage.py check_database_config

# Run database migrations before launching web server
echo "==> Running Django database migrations..."
python manage.py migrate --noinput

# Ensure persistent catalog and zero data loss on fresh PostgreSQL connections
echo "==> Verifying case catalog persistence..."
python manage.py ensure_persistent_data

# Ensure Paradise Eruption case and cropped item images exist
echo "==> Ensuring Paradise Eruption case catalog and media..."
python manage.py setup_paradise_eruption_case || true

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
