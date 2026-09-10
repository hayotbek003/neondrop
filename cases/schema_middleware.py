import logging
import threading
from django.core.management import call_command
from django.db import connection
from django.db.utils import ProgrammingError, OperationalError

logger = logging.getLogger('django')

_busy_lock = threading.Lock()
_checked = False


def ensure_schema_synchronized(force=False):
    global _checked
    if _checked and not force:
        return

    with _busy_lock:
        if _checked and not force:
            return

        try:
            from django.db.migrations.executor import MigrationExecutor
            executor = MigrationExecutor(connection)
            targets = executor.loader.graph.leaf_nodes()
            plan = executor.migration_plan(targets)

            if plan:
                logger.info(f"[NEONDROP SCHEMA SYNC] Found {len(plan)} unapplied migration(s). Applying now...")
                call_command('migrate', interactive=False)
                logger.info("[NEONDROP SCHEMA SYNC] All migrations successfully applied!")
            else:
                logger.info("[NEONDROP SCHEMA SYNC] Database schema is fully up to date.")

            _checked = True
        except Exception as e:
            logger.error(f"[NEONDROP SCHEMA SYNC] Warning during schema synchronization: {e}", exc_info=True)


class DatabaseSchemaSyncMiddleware:
    """
    Middleware that ensures database schema migrations are applied on production.
    If an UndefinedColumn / ProgrammingError occurs due to missing columns or tables,
    this middleware automatically applies pending migrations and retries the request.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        try:
            ensure_schema_synchronized()
        except Exception:
            pass

    def __call__(self, request):
        if not _checked:
            ensure_schema_synchronized()

        try:
            response = self.get_response(request)
            return response
        except (ProgrammingError, OperationalError) as exc:
            err_msg = str(exc).lower()
            if 'does not exist' in err_msg or 'undefinedcolumn' in err_msg or 'column' in err_msg:
                logger.warning(
                    f"[NEONDROP SCHEMA HEALER] Missing schema element encountered: {exc}. "
                    "Running live migrate to synchronize database..."
                )
                try:
                    ensure_schema_synchronized(force=True)
                    return self.get_response(request)
                except Exception as retry_exc:
                    logger.error(f"[NEONDROP SCHEMA HEALER] Auto-healing retry failed: {retry_exc}")
                    raise exc
            raise
