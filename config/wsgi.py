import os
import logging
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()

# Render / Ephemeral Container Startup Integrity Check
# Ensures core database tables exist before handling requests without touching application data
try:
    from django.db import connection
    from django.core.management import call_command

    with connection.cursor() as cursor:
        existing_tables = connection.introspection.table_names(cursor)

    if 'django_session' not in existing_tables or 'django_migrations' not in existing_tables:
        logging.getLogger('django').info("[NEONDROP] Missing core tables detected. Running automatic schema migrations...")
        call_command('migrate', interactive=False)
        logging.getLogger('django').info("[NEONDROP] Automatic schema migrations completed.")

    # Ensure admin privileges for admin and Smoke if user already exists
    try:
        call_command('promote_admin', 'admin', 'Smoke')
    except Exception:
        pass
except Exception as e:
    logging.getLogger('django').warning(f"[NEONDROP] Startup table check note: {e}")

