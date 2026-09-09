import os
import io
import json
import shutil
import zipfile
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile

from users.models import Profile, GoogleAccount
from payments.models import Transaction, CurrencySetting
from cases.models import Category, Item, Case, CaseItem, Opening, PromoCode
from inventory.models import InventoryItem
from cases.backup_restore_service import (
    create_full_backup_zip,
    inspect_backup_zip,
    restore_from_backup_zip,
    BackupRestoreError,
)


class AdminBackupRestoreTests(TestCase):
    """
    Comprehensive test suite verifying all 19 backup & restore requirements:
    - Admin GUI views (download, inspect preview, confirm restore)
    - ZIP file integrity and contents
    - Relational integrity, IDs, password hashes, balances, chances, prices
    - Media file backup and restoration
    - Idempotence (no duplicates on repeated restore)
    - Atomic rollback on errors
    """

    def setUp(self):
        self.temp_media_dir = tempfile.mkdtemp()
        self.client = Client()

        # Clean existing migration-seeded cases/items to ensure clean isolation
        Case.objects.all().delete()
        Item.objects.all().delete()

        # Create staff superuser
        self.admin_user = User.objects.create_superuser(
            username='Smoke',
            email='smoke@neondrop.gg',
            password='neondrop123'
        )
        self.admin_user.profile.balance = Decimal('550.75')
        self.admin_user.profile.save()

        # Create regular user
        self.player = User.objects.create_user(
            username='PlayerOne',
            email='player@neondrop.gg',
            password='SecretPlayerPass123!'
        )
        self.player.profile.balance = Decimal('120.00')
        self.player.profile.save()

        # Create Category, Case, and Items
        self.category = Category.objects.create(name='Категория Тест', slug='test-cat')
        self.item1 = Item.objects.create(
            weapon_type='AK-47',
            skin_name='Neon Rider',
            value=Decimal('75.50'),
            rarity='covert',
            rarity_color='#EB4B4B'
        )
        self.item2 = Item.objects.create(
            weapon_type='AWP',
            skin_name='Asiimov',
            value=Decimal('150.00'),
            rarity='classified',
            rarity_color='#D32CE6'
        )
        self.case = Case.objects.create(
            name='Cyber Neon Case',
            slug='cyber-neon-case',
            price=Decimal('50.00'),
            category=self.category,
            color_theme='cyber-pink',
            active=True
        )

        # Case items with EXACT weights
        self.case_item1 = CaseItem.objects.create(case=self.case, item=self.item1, weight=80.0)
        self.case_item2 = CaseItem.objects.create(case=self.case, item=self.item2, weight=20.0)

        # Opening record
        self.opening = Opening.objects.create(
            user=self.player,
            case=self.case,
            item=self.item1,
            price=Decimal('50.00'),
            server_seed='test_seed_123',
            client_seed='client_seed_456',
            server_seed_hash='hash789',
            nonce=1
        )

        # Inventory record
        self.inv = InventoryItem.objects.create(
            user=self.player,
            item=self.item1,
            opening=self.opening,
            is_sold=False,
            source='case'
        )

        # Transaction record
        self.tx = Transaction.objects.create(
            user=self.player,
            amount=Decimal('500.00'),
            balance_before=Decimal('0.00'),
            balance_after=Decimal('500.00'),
            transaction_type='deposit',
            status='completed',
            payment_method='card'
        )

        # PromoCode
        self.promo = PromoCode.objects.create(
            code='NEON2026',
            bonus_value=Decimal('50.00'),
            starts_at='2026-01-01T00:00:00Z',
            expires_at='2026-12-31T23:59:59Z'
        )

        # Sample media file
        sample_img_dir = Path(self.temp_media_dir) / 'cases'
        sample_img_dir.mkdir(parents=True, exist_ok=True)
        self.sample_img_path = sample_img_dir / 'cyber_case.png'
        with open(self.sample_img_path, 'wb') as f:
            f.write(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRtest_image_bytes')

    def tearDown(self):
        shutil.rmtree(self.temp_media_dir, ignore_errors=True)

    def test_01_download_backup_from_admin(self):
        """1. Скачать backup из Admin: GET endpoint returns 200 with zip attachment."""
        self.client.force_login(self.admin_user)
        url = reverse('admin_backup_download')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/zip')
        self.assertIn('neondrop_backup_', response['Content-Disposition'])

    def test_02_zip_file_opens_validly(self):
        """2. ZIP открывается и имеет правильный формат."""
        with override_settings(MEDIA_ROOT=self.temp_media_dir):
            archive_path, _ = create_full_backup_zip()
            self.assertTrue(os.path.exists(archive_path))
            self.assertTrue(zipfile.is_zipfile(archive_path))
            with zipfile.ZipFile(archive_path, 'r') as zipf:
                self.assertIn('database.json', zipf.namelist())
                self.assertIn('metadata.json', zipf.namelist())

    def test_03_backup_contains_all_models_and_media(self):
        """3. Backup содержит все необходимые модели и media."""
        with override_settings(MEDIA_ROOT=self.temp_media_dir):
            archive_path, metadata = create_full_backup_zip()
            with zipfile.ZipFile(archive_path, 'r') as zipf:
                db_data = json.loads(zipf.read('database.json').decode('utf-8'))
                models_in_backup = {obj['model'] for obj in db_data}
                
                self.assertIn('auth.user', models_in_backup)
                self.assertIn('users.profile', models_in_backup)
                self.assertIn('cases.case', models_in_backup)
                self.assertIn('cases.item', models_in_backup)
                self.assertIn('cases.caseitem', models_in_backup)
                self.assertIn('cases.opening', models_in_backup)
                self.assertIn('inventory.inventoryitem', models_in_backup)
                self.assertIn('payments.transaction', models_in_backup)
                self.assertIn('cases.promocode', models_in_backup)

                # Check media inclusion
                media_entries = [n for n in zipf.namelist() if n.startswith('media/')]
                self.assertTrue(len(media_entries) > 0)

    def test_04_05_upload_backup_and_inspect_preview(self):
        """4 & 5. Upload backup работает и preview показывает количество объектов."""
        with override_settings(MEDIA_ROOT=self.temp_media_dir):
            archive_path, _ = create_full_backup_zip()
            
            with open(archive_path, 'rb') as f:
                uploaded = SimpleUploadedFile(archive_path.name, f.read(), content_type='application/zip')

            self.client.force_login(self.admin_user)
            resp = self.client.post(reverse('admin_backup_restore'), {
                'action': 'inspect',
                'backup_file': uploaded
            })
            self.assertEqual(resp.status_code, 200)
            self.assertIn('preview', resp.context)
            preview = resp.context['preview']

            self.assertEqual(preview['users'], 2)  # Smoke + PlayerOne
            self.assertEqual(preview['cases'], 1)
            self.assertEqual(preview['items'], 2)
            self.assertEqual(preview['case_contents'], 2)
            self.assertEqual(preview['inventory'], 1)
            self.assertEqual(preview['openings'], 1)
            self.assertEqual(preview['transactions'], 1)
            self.assertEqual(preview['promocodes'], 1)

    def test_06_to_16_restore_preserves_all_relational_data_and_secrets(self):
        """
        6-16. Restore сохраняет:
        - User IDs
        - Password hashes
        - Балансы
        - Inventory
        - Cases
        - Items
        - Цены
        - Шансы (веса)
        - CaseContainments
        - Openings
        - Transactions
        """
        orig_smoke_hash = self.admin_user.password
        orig_player_hash = self.player.password
        orig_player_id = self.player.id
        orig_case_id = self.case.id
        orig_item1_id = self.item1.id

        with override_settings(MEDIA_ROOT=self.temp_media_dir):
            archive_path, _ = create_full_backup_zip()

            # Execute restore
            result = restore_from_backup_zip(archive_path, auto_backup=False, user=self.admin_user)
            self.assertTrue(result['success'])

            # 6. User IDs preserved
            player = User.objects.get(username='PlayerOne')
            self.assertEqual(player.id, orig_player_id)

            # 7. Password hashes preserved
            self.assertEqual(player.password, orig_player_hash)
            self.assertTrue(player.check_password('SecretPlayerPass123!'))
            smoke = User.objects.get(username='Smoke')
            self.assertEqual(smoke.password, orig_smoke_hash)
            self.assertTrue(smoke.check_password('neondrop123'))

            # 8. Balances preserved
            player.profile.refresh_from_db()
            self.assertEqual(player.profile.balance, Decimal('120.00'))
            smoke.profile.refresh_from_db()
            self.assertEqual(smoke.profile.balance, Decimal('550.75'))

            # 9. Inventory preserved
            inv_item = InventoryItem.objects.filter(user=player).first()
            self.assertIsNotNone(inv_item)
            self.assertEqual(inv_item.item.id, orig_item1_id)
            self.assertFalse(inv_item.is_sold)

            # 10 & 11 & 12. Cases, Items, Prices preserved
            case = Case.objects.get(id=orig_case_id)
            self.assertEqual(case.price, Decimal('50.00'))
            self.assertEqual(case.color_theme, 'cyber-pink')
            item1 = Item.objects.get(id=orig_item1_id)
            self.assertEqual(item1.value, Decimal('75.50'))

            # 13 & 14. Chances and CaseContainments preserved exactly
            ci1 = CaseItem.objects.get(case=case, item=item1)
            self.assertEqual(ci1.weight, 80.0)
            ci2 = CaseItem.objects.get(case=case, item=self.item2)
            self.assertEqual(ci2.weight, 20.0)

            # 15. Openings preserved
            op = Opening.objects.filter(user=player).first()
            self.assertIsNotNone(op)
            self.assertEqual(op.price, Decimal('50.00'))
            self.assertEqual(op.server_seed, 'test_seed_123')

            # 16. Transactions preserved
            tx = Transaction.objects.filter(user=player).first()
            self.assertIsNotNone(tx)
            self.assertEqual(tx.amount, Decimal('500.00'))
            self.assertEqual(tx.status, 'completed')

    def test_17_restore_restores_media(self):
        """17. Restore восстанавливает media файлы."""
        with override_settings(MEDIA_ROOT=self.temp_media_dir):
            archive_path, _ = create_full_backup_zip()

            # Delete the local file to simulate missing media
            if os.path.exists(self.sample_img_path):
                os.remove(self.sample_img_path)
            self.assertFalse(os.path.exists(self.sample_img_path))

            # Run restore
            restore_from_backup_zip(archive_path, auto_backup=False)

            # Media file must be restored
            self.assertTrue(os.path.exists(self.sample_img_path))
            with open(self.sample_img_path, 'rb') as f:
                content = f.read()
            self.assertIn(b'test_image_bytes', content)

    def test_18_repeated_restore_does_not_create_duplicates(self):
        """18. Повторный restore не создаёт дубликаты."""
        with override_settings(MEDIA_ROOT=self.temp_media_dir):
            archive_path, _ = create_full_backup_zip()

            count_users_before = User.objects.count()
            count_cases_before = Case.objects.count()
            count_items_before = Item.objects.count()

            # Run restore twice
            restore_from_backup_zip(archive_path, auto_backup=False)
            restore_from_backup_zip(archive_path, auto_backup=False)

            self.assertEqual(User.objects.count(), count_users_before)
            self.assertEqual(Case.objects.count(), count_cases_before)
            self.assertEqual(Item.objects.count(), count_items_before)

    def test_19_error_during_restore_rolls_back_atomically(self):
        """19. Ошибка Restore не оставляет базу в повреждённом состоянии."""
        with override_settings(MEDIA_ROOT=self.temp_media_dir):
            archive_path, _ = create_full_backup_zip()

            # Corrupt the zip data by creating an invalid database.json inside a test zip
            bad_zip_buffer = io.BytesIO()
            with zipfile.ZipFile(bad_zip_buffer, 'w') as zf:
                # Malformed JSON
                zf.writestr('database.json', '[{"model": "cases.case", "pk": 9999, "fields": {"price": "INVALID_NUMBER"}}]')
                zf.writestr('metadata.json', '{}')
            bad_zip_buffer.seek(0)

            initial_cases_count = Case.objects.count()
            with self.assertRaises(BackupRestoreError):
                restore_from_backup_zip(bad_zip_buffer, auto_backup=False)

            # Database must remain exactly as before
            self.assertEqual(Case.objects.count(), initial_cases_count)
