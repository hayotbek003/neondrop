import os
from pathlib import Path
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.contrib.auth.models import User
from django.conf import settings


class Command(BaseCommand):
    help = "Safely initializes a fresh PostgreSQL/SQLite database with existing production data without ever overwriting active data."

    def add_arguments(self, parser):
        parser.add_argument(
            '--force-seed',
            action='store_true',
            help='Force seed even if users exist (requires explicit intention)'
        )

    def handle(self, *args, **options):
        user_count = User.objects.count()

        if user_count > 0 and not options.get('force_seed'):
            self.stdout.write(
                self.style.SUCCESS(
                    f"[NEONDROP DB] Persistent database active: {user_count} users present. Skipping initial seed to protect existing data."
                )
            )
            # Ensure Smoke is always superuser & staff
            try:
                call_command('promote_admin', 'Smoke')
            except Exception:
                pass
            return

        self.stdout.write(
            self.style.WARNING(
                "[NEONDROP DB] Fresh/Empty database detected (0 users). Initiating zero-loss seed from existing production dataset..."
            )
        )

        fixture_file = settings.BASE_DIR / 'cases' / 'fixtures' / 'initial_data.json'
        if not fixture_file.exists():
            # Fallback to backups directory if exists
            backups_dir = settings.BASE_DIR / 'backups' / 'database'
            json_files = sorted(backups_dir.glob('*.json')) if backups_dir.exists() else []
            if json_files:
                fixture_file = json_files[-1]

        if fixture_file and fixture_file.exists():
            self.stdout.write(f" -> Restoring production data from: {fixture_file}")
            call_command('restore_data', str(fixture_file), ignore_checksum=True)
            
            # Ensure Smoke has admin privileges
            call_command('promote_admin', 'Smoke')
            
            self.stdout.write(
                self.style.SUCCESS(
                    "[NEONDROP DB] Zero-loss migration to database completed successfully!"
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR(
                    "[NEONDROP DB] No initial data fixture found. Please create one with `python manage.py backup_data`."
                )
            )
