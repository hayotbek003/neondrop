import os
import tarfile
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

class Command(BaseCommand):
    help = "Restores a compressed .tar.gz media backup into MEDIA_ROOT."

    def add_arguments(self, parser):
        parser.add_argument(
            'archive_file',
            type=str,
            help='Path to the media backup archive (.tar.gz)'
        )
        parser.add_argument(
            '--target',
            type=str,
            help='Custom target directory (default: settings.MEDIA_ROOT)'
        )

    def handle(self, *args, **options):
        archive_path = Path(options['archive_file'])
        if not archive_path.exists():
            raise CommandError(f"Media archive not found: {archive_path.resolve()}")

        target_dir = Path(options['target']) if options.get('target') else Path(settings.MEDIA_ROOT)
        target_dir.mkdir(parents=True, exist_ok=True)

        self.stdout.write(self.style.NOTICE(f"\n[NEONDROP MEDIA RESTORE] Extracting {archive_path.name} into {target_dir.resolve()}..."))

        extracted_count = 0
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                members = tar.getmembers()
                for member in members:
                    # Prevent directory traversal attacks
                    target_file = (target_dir / member.name).resolve()
                    if not str(target_file).startswith(str(target_dir.resolve())):
                        raise CommandError(f"Security error: Archive contains illegal relative path: {member.name}")
                    
                    tar.extract(member, path=target_dir)
                    if member.isfile():
                        extracted_count += 1
                        self.stdout.write(f"  + Extracted: {member.name}")
        except Exception as e:
            raise CommandError(f"Failed to extract media archive: {e}")

        self.stdout.write(self.style.SUCCESS("\n" + "=" * 65))
        self.stdout.write(self.style.SUCCESS(f" [SUCCESS] Media Restoration Complete!"))
        self.stdout.write(self.style.SUCCESS("=" * 65))
        self.stdout.write(f" Target Directory: {target_dir.resolve()}")
        self.stdout.write(f" Total Extracted:  {extracted_count} files")
        self.stdout.write("=" * 65 + "\n")
