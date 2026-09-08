import sys
from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import connection


class Command(BaseCommand):
    help = "Inspects active database configuration and warns if running on an ephemeral SQLite disk on Render."

    def handle(self, *args, **options):
        db_settings = settings.DATABASES['default']
        engine = db_settings.get('ENGINE', '')
        name = db_settings.get('NAME', '')
        host = db_settings.get('HOST', '') or 'localhost'
        port = db_settings.get('PORT', '') or 'default'
        user = db_settings.get('USER', '') or 'none'

        is_postgres = 'postgresql' in engine
        is_sqlite = 'sqlite' in engine

        # Test database connectivity
        db_connected = False
        connection_error = None
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            db_connected = True
        except Exception as e:
            connection_error = str(e)

        conn_status = 'YES (Healthy)' if db_connected else f'NO (Error: {connection_error})'

        self.stdout.write("\n" + "=" * 70)
        self.stdout.write("  NEONDROP DATABASE CONFIGURATION CHECK")
        self.stdout.write("=" * 70)
        self.stdout.write(f"  Engine:        {engine}")
        self.stdout.write(f"  Database Name: {name}")
        self.stdout.write(f"  Host:          {host} (Port: {port})")
        self.stdout.write(f"  User:          {user}")
        self.stdout.write(f"  Connected:     {conn_status}")

        if is_postgres:
            self.stdout.write(self.style.SUCCESS("  Persistence:   PERSISTENT [PostgreSQL]"))
            self.stdout.write(self.style.SUCCESS("  Verdict:       SAFE - Data persists across all Render spin-downs & restarts!"))
        elif is_sqlite:
            self.stdout.write(self.style.ERROR("  Persistence:   EPHEMERAL [SQLite]"))
            self.stdout.write(self.style.WARNING("  Verdict:       WARNING - SQLite database on container disk is wiped on Render spin-down!"))
            self.stdout.write(self.style.WARNING("  ACTION:        Ensure DATABASE_URL is set to PostgreSQL (neondrop-db) in Render Dashboard!"))
        else:
            self.stdout.write(f"  Persistence:   CUSTOM [{engine}]")

        # Query stats if connected and tables exist
        if db_connected:
            try:
                from django.contrib.auth.models import User
                from cases.models import Case, Item, Opening
                from payments.models import Transaction

                self.stdout.write("-" * 70)
                self.stdout.write("  CURRENT RECORD COUNTS:")
                self.stdout.write(f"    Users:        {User.objects.count()}")
                self.stdout.write(f"    Cases:        {Case.objects.count()}")
                self.stdout.write(f"    Items:        {Item.objects.count()}")
                self.stdout.write(f"    Openings:     {Opening.objects.count()}")
                self.stdout.write(f"    Transactions: {Transaction.objects.count()}")
            except Exception as stat_err:
                self.stdout.write(f"    (Record count note: migrations pending or tables not yet created: {stat_err})")

        self.stdout.write("=" * 70 + "\n")
