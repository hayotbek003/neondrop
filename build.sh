#!/usr/bin/env bash
# Exit on error
set -o errexit

pip install -r requirements.txt

# collectstatic does not require DATABASE_URL — safe to run during build phase.
# NOTE: migrations are intentionally NOT run here.
# DATABASE_URL is a runtime-only env var on Render and is NOT available during build.
# Migrations run in start.sh when the container starts with all env vars available.
python manage.py collectstatic --noinput
