import os
import tarfile
from datetime import datetime
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

class Command(BaseCommand):
    help = "Creates a compressed .tar.gz backup of all user and case media assets (MEDIA_ROOT)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            type=str,
            help='Custom output path for the media archive (default: backups/media/neondrop_media_YYYYMMDD_HHMMSS.tar.gz)'
        )

    def handle(self, *args, **options):
        media_root = Path(settings.MEDIA_ROOT)
        media_root.mkdir(parents=True, exist_ok=True)

        backups_dir = settings.BASE_DIR / 'backups' / 'media'
        backups_dir.mkdir(parents=True, exist_ok=True)

        timestamp_str = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        default_filename = f"neondrop_media_{timestamp_str}.tar.gz"
        output_path = Path(options['output']) if options.get('output') else (backups_dir / default_filename)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        self.stdout.write(self.style.NOTICE(f"\n[NEONDROP MEDIA BACKUP] Archiving files from {media_root.resolve()}..."))

        all_files = [p for p in media_root.rglob('*') if p.is_file()]
        total_files = len(all_files)
        total_bytes = sum(p.stat().st_size for p in all_files)

        with tarfile.open(output_path, "w:gz") as tar:
            for file_path in all_files:
                arcname = file_path.relative_to(media_root)
                tar.add(file_path, arcname=str(arcname))
                self.stdout.write(f"  + Added: {arcname}")

        file_size_kb = output_path.stat().st_size / 1024.0

        self.stdout.write(self.style.SUCCESS("\n" + "=" * 65))
        self.stdout.write(self.style.SUCCESS(f" [SUCCESS] Media Archive Created!"))
        self.stdout.write(self.style.SUCCESS("=" * 65))
        self.stdout.write(f" Archive Location: {output_path.resolve()}")
        self.stdout.write(f" Total Files:      {total_files}")
        self.stdout.write(f" Raw Media Size:   {total_bytes / 1024.0:.2f} KB")
        self.stdout.write(f" Archive Size:     {file_size_kb:.2f} KB")
        self.stdout.write("=" * 65 + "\n")
