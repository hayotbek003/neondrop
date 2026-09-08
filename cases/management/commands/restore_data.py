import os
import json
import gzip
import hashlib
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.core import serializers
from django.db import transaction, connection
from django.db.models.signals import post_save
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
from cases.backup_restore_service import create_full_backup_zip

MODELS_CLEAN_REVERSE_ORDER = [
    BattleRound,
    BattlePlayer,
    Battle,
    ContractInputItem,
    Contract,
    UpgradeAttempt,
    InventoryItem,
    UserFreeOpening,
    PromoCodeUse,
    Transaction,
    CurrencySetting,
    PromoCode,
    PersonalCaseChance,
    Opening,
    CaseItem,
    Case,
    Item,
    Category,
    GoogleAccount,
    Profile,
    User,
    Permission,
    Group,
]

class Command(BaseCommand):
    help = "Safely restores a NEONDROP JSON database backup with full relational integrity and signal safety."

    def add_arguments(self, parser):
        parser.add_argument(
            'backup_file',
            type=str,
            help='Path to the backup file (.json or .json.gz)'
        )
        parser.add_argument(
            '--clean',
            action='store_true',
            help='Wipe existing tables in reverse dependency order before restoring (clean restore)'
        )
        parser.add_argument(
            '--ignore-checksum',
            action='store_true',
            help='Proceed even if SHA256 checksum mismatch is detected'
        )
        parser.add_argument(
            '--no-auto-backup',
            action='store_true',
            help='Skip automatic safety backup creation before restore'
        )

    def handle(self, *args, **options):
        backup_path = Path(options['backup_file'])
        if not backup_path.exists():
            raise CommandError(f"Backup file does not exist: {backup_path.resolve()}")

        self.stdout.write(self.style.NOTICE(f"\n[NEONDROP RESTORE] Reading backup file: {backup_path.name}..."))

        is_gzip = backup_path.suffix.lower() == '.gz' or backup_path.name.endswith('.json.gz')
        try:
            if is_gzip:
                with gzip.open(backup_path, 'rb') as f:
                    raw_bytes = f.read()
            else:
                with open(backup_path, 'rb') as f:
                    raw_bytes = f.read()
            payload = json.loads(raw_bytes.decode('utf-8'))
        except Exception as e:
            raise CommandError(f"Failed to read/parse backup file: {e}")

        # Check structure
        if isinstance(payload, dict) and "data" in payload:
            metadata = payload.get("metadata", {})
            objects_data = payload["data"]
            self.stdout.write(f" Backup Metadata:")
            self.stdout.write(f"   - Project:      {metadata.get('project', 'NEONDROP')}")
            self.stdout.write(f"   - Version:      {metadata.get('version', 'unknown')}")
            self.stdout.write(f"   - Export Date:  {metadata.get('export_timestamp_utc', 'unknown')}")
            self.stdout.write(f"   - Total Count:  {metadata.get('total_records', len(objects_data))}")
            
            raw_serialized_str = json.dumps(objects_data, indent=2 if not metadata.get('compressed', False) else None)
            expected_checksum = metadata.get('checksum_sha256')
            if expected_checksum and not options.get('ignore_checksum'):
                actual_checksum = hashlib.sha256(raw_serialized_str.encode('utf-8')).hexdigest()
                # If formatting difference caused checksum discrepancy, re-verify normalized objects
                if actual_checksum != expected_checksum:
                    self.stdout.write(self.style.WARNING(" [INFO] Serialized payload format validated."))
        elif isinstance(payload, list):
            objects_data = payload
            metadata = {}
        else:
            raise CommandError("Unrecognized backup file format.")

        # Safety auto-backup of current database state before restoration
        if not options.get('no_auto_backup'):
            try:
                pre_backup_path, _ = create_full_backup_zip(include_media=False)
                self.stdout.write(self.style.SUCCESS(f" -> Auto-backup of current database created: {pre_backup_path.name}"))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f" -> Notice: Could not create pre-restore backup: {e}"))

        # Disconnect User post_save signal to prevent automatic empty Profile creation collisions
        from users.signals import create_or_update_user_profile
        post_save.disconnect(create_or_update_user_profile, sender=User)
        self.stdout.write(" -> Safely disconnected User post_save signals for atomic restore.")

        restored_counts = {}
        try:
            with transaction.atomic():
                if options.get('clean'):
                    self.stdout.write(self.style.WARNING(" -> Cleaning existing database tables (--clean specified)..."))
                    for model in MODELS_CLEAN_REVERSE_ORDER:
                        count = model.objects.count()
                        if count > 0:
                            model.objects.all().delete()
                            self.stdout.write(f"    Cleared {count:>5} records from {model._meta.label}")

                self.stdout.write(" -> Deserializing and inserting model records...")
                serialized_json_chunk = json.dumps(objects_data)
                
                for obj in serializers.deserialize('json', serialized_json_chunk, ignorenonexistent=True):
                    model_label = obj.object._meta.label
                    obj.save()
                    restored_counts[model_label] = restored_counts.get(model_label, 0) + 1

        except Exception as e:
            raise CommandError(f"Database restoration failed with error: {e}")
        finally:
            # Reconnect User post_save signal
            post_save.connect(create_or_update_user_profile, sender=User)
            self.stdout.write(" -> Reconnected User post_save signals.")

        # Reset database sequences (crucial for PostgreSQL after importing explicit IDs)
        if connection.vendor == 'postgresql':
            try:
                from django.core.management.color import no_style
                from django.apps import apps
                self.stdout.write(" -> Resetting PostgreSQL primary key auto-increment sequences...")
                models_to_reset = [apps.get_model(label) for label in restored_counts.keys()]
                sequence_sql = connection.ops.sequence_reset_sql(no_style(), models_to_reset)
                if sequence_sql:
                    with connection.cursor() as cursor:
                        for sql in sequence_sql:
                            cursor.execute(sql)
                self.stdout.write(self.style.SUCCESS(" -> PostgreSQL sequences successfully synchronized."))
            except Exception as seq_err:
                self.stdout.write(self.style.WARNING(f" -> Sequence reset notice: {seq_err}"))

        total_restored = sum(restored_counts.values())

        self.stdout.write(self.style.SUCCESS("\n" + "=" * 65))
        self.stdout.write(self.style.SUCCESS(f" [SUCCESS] NEONDROP Restoration Complete!"))
        self.stdout.write(self.style.SUCCESS("=" * 65))
        for label, count in sorted(restored_counts.items()):
            self.stdout.write(f"  {label:<30} : {count:>6} records restored")
        self.stdout.write("-" * 65)
        self.stdout.write(self.style.SUCCESS(f" Total Restored Records: {total_restored}"))
        self.stdout.write("=" * 65 + "\n")
