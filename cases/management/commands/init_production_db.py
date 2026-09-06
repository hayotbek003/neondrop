import os
from pathlib import Path
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.contrib.auth.models import User
from django.conf import settings


class Command(BaseCommand):
    help = "Manual helper to seed or restore data on a fresh database. Safe by default: refuses to run if data already exists."

    def add_arguments(self, parser):
        parser.add_argument(
            '--force-seed',
            action='store_true',
            help='Force seed even if cases or users exist'
        )

    def handle(self, *args, **options):
        user_count = User.objects.count()

        if user_count > 0 and not options.get('force_seed'):
            self.stdout.write(
                self.style.WARNING(
                    f"[NEONDROP DB PROTECT] Database contains {user_count} users and active case data.\n"
                    f"Automatic seed/fixture restoration is disabled to prevent overwriting admin changes.\n"
                    f"Use `python manage.py seed_initial_data --force` only if you intentionally want to reseed."
                )
            )
            return

        if not options.get('force_seed'):
            self.stdout.write(
                self.style.WARNING(
                    "[NEONDROP DB PROTECT] To populate an empty database with default cases, run:\n"
                    "  python manage.py seed_initial_data\n"
                    "Or to restore a backup:\n"
                    "  python manage.py restore_data <path_to_backup.json>"
                )
            )
            return

        fixture_file = settings.BASE_DIR / 'cases' / 'fixtures' / 'initial_data.json'
        if fixture_file.exists():
            self.stdout.write(f" -> Restoring production data from: {fixture_file}")
            call_command('restore_data', str(fixture_file), ignore_checksum=True)
            try:
                call_command('promote_admin', 'Smoke')
            except Exception:
                pass
