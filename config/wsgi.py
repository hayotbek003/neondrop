import os
import logging
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()

# Render / Ephemeral Container Startup Integrity Check
# Ensures that even if the container starts fresh with an empty SQLite database,
# Django automatically runs migrations and creates django_session before handling requests.
try:
    from django.db import connection
    from django.core.management import call_command

    with connection.cursor() as cursor:
        existing_tables = connection.introspection.table_names(cursor)

    if 'django_session' not in existing_tables or 'django_migrations' not in existing_tables:
        logging.getLogger('django').info("[NEONDROP] Missing core tables detected. Running automatic startup migrations...")
        call_command('migrate', interactive=False)
        logging.getLogger('django').info("[NEONDROP] Automatic startup migrations completed successfully.")

    # Ensure admin privileges for Smoke
    try:
        call_command('promote_admin', 'Smoke')
    except Exception:
        pass
except Exception as e:
    logging.getLogger('django').warning(f"[NEONDROP] Startup table check note: {e}")

