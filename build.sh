#!/usr/bin/env bash
# Exit on error
set -o errexit

pip install -r requirements.txt

# collectstatic does not require DATABASE_URL — safe to run during build phase.
# NOTE: migrations are intentionally NOT run here.
# DATABASE_URL is a runtime-only env var on Render and is NOT available during build.
python manage.py collectstatic --noinput

# If DATABASE_URL is available during build phase, execute migrations immediately
if [ -n "$DATABASE_URL" ]; then
    echo "==> DATABASE_URL detected during build phase. Running migrations..."
    python manage.py migrate --noinput || echo "==> Migrations during build failed or deferred to runtime startup."
fi
