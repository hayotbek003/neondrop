import os
import json
import gzip
import hashlib
from datetime import datetime
from pathlib import Path
from django.core.management.base import BaseCommand
from django.core import serializers
from django.conf import settings
from django.contrib.auth.models import User, Group, Permission
from django.contrib.sessions.models import Session
from users.models import Profile, GoogleAccount
from cases.models import (
    Category, Item, Case, CaseItem, Opening,
    PersonalCaseChance, PromoCode, PromoCodeUse, UserFreeOpening
)
from inventory.models import InventoryItem
from payments.models import Transaction, CurrencySetting
from upgrades.models import UpgradeAttempt
from contracts.models import Contract, ContractInputItem
from battles.models import Battle, BattlePlayer, BattleRound

MODELS_EXPORT_ORDER = [
    ('auth.Group', Group),
    ('auth.Permission', Permission),
    ('auth.User', User),
    ('users.Profile', Profile),
    ('users.GoogleAccount', GoogleAccount),
    ('payments.CurrencySetting', CurrencySetting),
    ('cases.Category', Category),
    ('cases.Item', Item),
    ('cases.Case', Case),
    ('cases.CaseItem', CaseItem),
    ('cases.Opening', Opening),
    ('cases.PersonalCaseChance', PersonalCaseChance),
    ('cases.PromoCode', PromoCode),
    ('payments.Transaction', Transaction),
    ('cases.PromoCodeUse', PromoCodeUse),
    ('cases.UserFreeOpening', UserFreeOpening),
    ('inventory.InventoryItem', InventoryItem),
    ('upgrades.UpgradeAttempt', UpgradeAttempt),
    ('contracts.Contract', Contract),
    ('contracts.ContractInputItem', ContractInputItem),
    ('battles.Battle', Battle),
    ('battles.BattlePlayer', BattlePlayer),
    ('battles.BattleRound', BattleRound),
]

class Command(BaseCommand):
    help = "Creates a comprehensive, zero-data-loss JSON database backup for NEONDROP migration."

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            type=str,
            help='Custom output path for the backup file (default: backups/database/neondrop_db_YYYYMMDD_HHMMSS.json)'
        )
        parser.add_argument(
            '--compress',
            action='store_true',
            help='Compress backup output using Gzip (.json.gz)'
        )
        parser.add_argument(
            '--include-sessions',
            action='store_true',
            help='Include active user HTTP sessions in the backup'
        )

    def handle(self, *args, **options):
        timestamp_str = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        backups_dir = settings.BASE_DIR / 'backups' / 'database'
        backups_dir.mkdir(parents=True, exist_ok=True)

        is_compressed = options['compress']
        ext = '.json.gz' if is_compressed else '.json'
        default_filename = f"neondrop_db_{timestamp_str}{ext}"
        
        output_path = Path(options['output']) if options.get('output') else (backups_dir / default_filename)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        self.stdout.write(self.style.NOTICE(f"\n[NEONDROP BACKUP] Starting database export at {datetime.utcnow().isoformat()}Z..."))

        export_models = list(MODELS_EXPORT_ORDER)
        if options.get('include_sessions'):
            export_models.append(('sessions.Session', Session))

        all_objects = []
        record_counts = {}
        total_records = 0

        for label, model in export_models:
            qs = model.objects.all().order_by('pk')
            count = qs.count()
            record_counts[label] = count
            total_records += count
            if count > 0:
                all_objects.extend(list(qs))
            self.stdout.write(f"  -> Extracted {count:>6} records from {label}")

        # Serialize using Django JSON serializer
        raw_json_str = serializers.serialize(
            'json',
            all_objects,
            indent=2 if not is_compressed else None,
            use_natural_foreign_keys=False,
            use_natural_primary_keys=False
        )

        checksum_sha256 = hashlib.sha256(raw_json_str.encode('utf-8')).hexdigest()

        backup_payload = {
            "metadata": {
                "project": "NEONDROP",
                "version": "2.0.0",
                "export_timestamp_utc": datetime.utcnow().isoformat() + "Z",
                "database_engine": settings.DATABASES['default'].get('ENGINE', 'unknown'),
                "total_records": total_records,
                "record_counts": record_counts,
                "checksum_sha256": checksum_sha256,
                "compressed": is_compressed,
            },
            "data": json.loads(raw_json_str)
        }

        final_json_bytes = json.dumps(backup_payload, indent=2 if not is_compressed else None).encode('utf-8')

        if is_compressed:
            with gzip.open(output_path, 'wb') as f:
                f.write(final_json_bytes)
        else:
            with open(output_path, 'wb') as f:
                f.write(final_json_bytes)

        file_size_kb = output_path.stat().st_size / 1024.0

        self.stdout.write(self.style.SUCCESS("\n" + "=" * 65))
        self.stdout.write(self.style.SUCCESS(f" [SUCCESS] NEONDROP Database Backup Created!"))
        self.stdout.write(self.style.SUCCESS("=" * 65))
        self.stdout.write(f" File Location: {output_path.resolve()}")
        self.stdout.write(f" File Size:     {file_size_kb:.2f} KB")
        self.stdout.write(f" Total Records: {total_records}")
        self.stdout.write(f" SHA256 Check:  {checksum_sha256}")
        self.stdout.write("=" * 65 + "\n")
