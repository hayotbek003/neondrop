import os
import logging
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()

# Render / Ephemeral Container Startup Integrity Check
# Ensures core database tables and all pending schema migrations are applied on startup
try:
    from django.db import connection
    from django.core.management import call_command
    from cases.schema_middleware import ensure_schema_synchronized

    try:
        ensure_schema_synchronized(force=True)
    except Exception as me:
        logging.getLogger('django').error(f"[NEONDROP] Startup migration notice: {me}", exc_info=True)

    # Ensure case catalog exists without touching existing data
    try:
        call_command('ensure_persistent_data')
    except Exception:
        pass

    # Ensure Smoke has admin privileges — password is NEVER changed.
    try:
        call_command('promote_admin', 'Smoke')
    except Exception:
        pass
    # Ensure 'admin' superuser exists (uses ADMIN_PASSWORD env var if set).
    try:
        call_command('promote_admin', 'admin', '--update-existing')
    except Exception:
        pass
except Exception as e:
    logging.getLogger('django').warning(f"[NEONDROP] Startup table check note: {e}")

