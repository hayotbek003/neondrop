import os
from pathlib import Path
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.contrib.auth.models import User
from django.conf import settings


class Command(BaseCommand):
    help = "Initializes production database safely: if database is empty, takes backup and restores verified snapshot."

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force restore even if users exist'
        )

    def handle(self, *args, **options):
        user_count = User.objects.count()

        if user_count > 0 and not options.get('force'):
            self.stdout.write(
                self.style.SUCCESS(
                    f"[NEONDROP DB PROTECT] Production database already contains {user_count} users.\n"
                    "Automatic restore is skipped to preserve production data."
                )
            )
            return

        self.stdout.write(
            self.style.NOTICE(
                f"[NEONDROP DB RESTORE] Database has {user_count} users. Initiating automatic snapshot restoration..."
            )
        )

        # 1. Take a pre-restore backup of the current database state
        self.stdout.write(" -> Step 1: Taking pre-restore backup of current database state...")
        try:
            call_command('backup_data')
            self.stdout.write(self.style.SUCCESS(" -> Pre-restore backup completed."))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f" -> Pre-restore backup notice: {e}"))

        # 2. Restore verified snapshot
        snapshot_file = settings.BASE_DIR / 'backups' / 'database' / 'neondrop_db_20260906_172418.json'
        if snapshot_file.exists():
            self.stdout.write(f" -> Step 2: Restoring verified snapshot: {snapshot_file}")
            call_command('restore_data', str(snapshot_file))
            self.stdout.write(self.style.SUCCESS(" -> Verified snapshot restored successfully!"))
        else:
            self.stdout.write(self.style.ERROR(f" -> Snapshot file not found: {snapshot_file}"))
            return

        # 3. Verify / ensure Smoke admin privileges
        try:
            self.stdout.write(" -> Step 3: Verifying admin privileges for Smoke...")
            call_command('promote_admin', 'Smoke')
        except Exception as e:
            self.stdout.write(self.style.WARNING(f" -> Promote admin notice: {e}"))

