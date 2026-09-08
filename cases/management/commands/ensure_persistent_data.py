import os
from pathlib import Path
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.conf import settings
from cases.models import Case


class Command(BaseCommand):
    help = "Ensures case catalog and essential records exist without ever overwriting active data."

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force population even if cases exist (requires explicit intention)'
        )

    def handle(self, *args, **options):
        case_count = Case.objects.count()

        if case_count > 0 and not options.get('force'):
            self.stdout.write(
                self.style.SUCCESS(
                    f"[NEONDROP PERSISTENCE] Database contains {case_count} active cases. "
                    f"Zero data loss protection active: skipping initial data restore."
                )
            )
            return

        self.stdout.write(
            self.style.WARNING(
                "[NEONDROP PERSISTENCE] Empty case catalog detected (0 cases). "
                "Populating original 8 cases & 27 items from production initial dataset..."
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
            self.stdout.write(f" -> Restoring production data from: {fixture_file.name}")
            call_command(
                'restore_data',
                str(fixture_file),
                ignore_checksum=True,
                no_auto_backup=True
            )
            
            # Ensure Smoke admin privileges
            try:
                call_command('promote_admin', 'Smoke')
            except Exception as e:
                self.stdout.write(self.style.WARNING(f" -> Smoke admin check: {e}"))

            # Ensure admin superuser if env var set
            try:
                call_command('promote_admin', 'admin', '--update-existing')
            except Exception as e:
                self.stdout.write(self.style.WARNING(f" -> Admin check: {e}"))

            new_case_count = Case.objects.count()
            self.stdout.write(
                self.style.SUCCESS(
                    f"[NEONDROP PERSISTENCE] Successfully initialized catalog! Total active cases: {new_case_count}."
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR(
                    "[NEONDROP PERSISTENCE] Initial data fixture not found. "
                    "Cannot populate initial case catalog."
                )
            )
