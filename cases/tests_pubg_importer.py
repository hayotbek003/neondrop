import io
import json
import zipfile
import tempfile
from decimal import Decimal
from pathlib import Path

from unittest.mock import patch
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from cases.models import Item, PubgImportSession
from users.models import AdminPermissionProfile
from cases.pubg_importer_service import (
    PubgZipImporter,
    PubgImportValidationError,
    normalize_url,
    map_pubg_rarity,
    get_pubg_import_storage_dir,
)


def create_test_zip(items_data, image_files=None):
    """
    Helper to construct an in-memory ZIP archive with items.json and dummy images.
    """
    zip_buffer = io.BytesIO()
    # 1x1 transparent PNG / dummy image bytes
    dummy_img_bytes = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82'

    with zipfile.ZipFile(zip_buffer, 'w') as zf:
        zf.writestr('items.json', json.dumps(items_data, ensure_ascii=False))
        if image_files:
            for path in image_files:
                zf.writestr(path, dummy_img_bytes)

    zip_buffer.seek(0)
    return zip_buffer


class PubgZipImporterServiceTestCase(TestCase):
    def setUp(self):
        self.dummy_img = "images/item_test_01.webp"

    def test_normalize_url(self):
        """Verify URL normalization strips whitespace, trailing slashes, and lowercases host."""
        self.assertEqual(normalize_url("  HTTPS://Example.COM/item/123/  "), "https://example.com/item/123")
        self.assertEqual(normalize_url("http://shop.com/pubg/skin"), "http://shop.com/pubg/skin")
        self.assertEqual(normalize_url(""), "")
        self.assertEqual(normalize_url(None), "")

    def test_map_pubg_rarity(self):
        """Verify rarity mapping for PUBG and standard tiers."""
        code, color = map_pubg_rarity("Mythic")
        self.assertEqual(code, 'mythic')
        self.assertEqual(color, '#FFD700')

        code, color = map_pubg_rarity("Легендарный")
        self.assertEqual(code, 'legendary')
        self.assertEqual(color, '#EB4B4B')

        code, color = map_pubg_rarity("Epic")
        self.assertEqual(code, 'epic')

        code, color = map_pubg_rarity("Rare")
        self.assertEqual(code, 'rare')

        code, color = map_pubg_rarity("UnknownRarity")
        self.assertEqual(code, 'rare')  # Default fallback

    def test_valid_zip_import_add_only(self):
        """Verify importing a valid ZIP file creates items and saves images in add_only mode."""
        items = [{
            "game": "PUBG",
            "name": "BAPE Camo Shark Hoodie",
            "price": 250.00,
            "rarity": "Legendary",
            "quality": "Pristine",
            "type": "outfit",
            "image": "images/item_01.webp",
            "source_url": "https://pubgitems.com/item/bape-camo",
            "source_image_url": "https://pubgitems.com/images/bape-camo.webp",
            "source_id": "pubg_src_1001"
        }]
        zip_buf = create_test_zip(items, ["images/item_01.webp"])

        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tf:
            tf.write(zip_buf.getvalue())
            temp_path = tf.name

        try:
            importer = PubgZipImporter(temp_path)
            inspection = importer.validate_and_inspect()
            self.assertTrue(inspection['is_valid'])
            self.assertEqual(inspection['total_items'], 1)
            self.assertEqual(inspection['new_items'], 1)
            self.assertEqual(inspection['existing_items'], 0)

            # Execute import
            summary = importer.execute_import(mode='add_only')
            self.assertTrue(summary['success'])
            self.assertEqual(summary['created'], 1)
            self.assertEqual(summary['skipped'], 0)
            self.assertEqual(summary['images_saved'], 1)

            # Verify in DB
            db_item = Item.objects.filter(source_id="pubg_src_1001").first()
            self.assertIsNotNone(db_item)
            self.assertEqual(db_item.name, "BAPE Camo Shark Hoodie")
            self.assertEqual(db_item.game, "PUBG")
            self.assertEqual(db_item.value, Decimal("250.00"))
            self.assertEqual(db_item.rarity, "legendary")
            self.assertEqual(db_item.quality, "Pristine")
            self.assertEqual(db_item.item_type, "outfit")
            self.assertEqual(db_item.source_url, "https://pubgitems.com/item/bape-camo")
            self.assertTrue(bool(db_item.image))
            self.assertTrue(Path(db_item.image.path).exists())

        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_duplicate_prevention_on_repeat_import(self):
        """Verify re-uploading the same ZIP does not create duplicates and increments skipped."""
        items = [{
            "game": "PUBG",
            "name": "M416 The Fool",
            "price": 1200.00,
            "rarity": "Mythic",
            "quality": "Flawless",
            "type": "weapon",
            "image": "images/m416.webp",
            "source_id": "fool_m416_01"
        }]
        zip_buf = create_test_zip(items, ["images/m416.webp"])

        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tf:
            tf.write(zip_buf.getvalue())
            temp_path = tf.name

        try:
            importer = PubgZipImporter(temp_path)
            # First import: creates 1
            res1 = importer.execute_import(mode='add_only')
            self.assertEqual(res1['created'], 1)
            self.assertEqual(res1['skipped'], 0)
            initial_count = Item.objects.count()

            # Second import: skips 1, creates 0
            res2 = importer.execute_import(mode='add_only')
            self.assertEqual(res2['created'], 0)
            self.assertEqual(res2['skipped'], 1)
            self.assertEqual(Item.objects.count(), initial_count)

        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_matching_priority_source_id_then_url_then_name(self):
        """Verify the 3-step hierarchy: 1. source_id, 2. source_url, 3. name + game."""
        # 1. Existing item matched by source_id even if name changed
        item1 = Item.objects.create(
            name="Original Name",
            value=Decimal("100.00"),
            source_id="src_match_priority_1",
            game="PUBG"
        )
        match_obj, match_type, _ = PubgZipImporter.find_existing_item({
            "name": "Completely Different Name",
            "source_id": "src_match_priority_1",
            "game": "PUBG"
        })
        self.assertEqual(match_type, 'source_id')
        self.assertEqual(match_obj.id, item1.id)

        # 2. Existing item matched by normalized source_url when source_id is missing
        item2 = Item.objects.create(
            name="URL Item",
            value=Decimal("200.00"),
            source_url="https://market.pubg.com/items/555",
            game="PUBG"
        )
        match_obj2, match_type2, _ = PubgZipImporter.find_existing_item({
            "name": "Different Name Too",
            "source_url": "HTTPS://market.pubg.com/items/555/",
            "game": "PUBG"
        })
        self.assertEqual(match_type2, 'source_url')
        self.assertEqual(match_obj2.id, item2.id)

        # 3. Fallback matched by name + game
        item3 = Item.objects.create(
            name="Kar98k - Dragonfire",
            value=Decimal("350.00"),
            game="PUBG"
        )
        match_obj3, match_type3, _ = PubgZipImporter.find_existing_item({
            "name": "Kar98k - Dragonfire",
            "game": "PUBG"
        })
        self.assertEqual(match_type3, 'name_game')
        self.assertEqual(match_obj3.id, item3.id)

    def test_update_existing_mode(self):
        """Verify update_existing mode updates price, rarity, quality, type and image."""
        item = Item.objects.create(
            name="PUBG Dacia - Police",
            value=Decimal("50.00"),
            rarity="common",
            source_id="dacia_001",
            game="PUBG"
        )

        update_data = [{
            "game": "PUBG",
            "name": "PUBG Dacia - Police",
            "price": 150.00,  # updated price
            "rarity": "Epic", # updated rarity
            "quality": "Special",
            "type": "vehicle",
            "image": "images/dacia.webp",
            "source_id": "dacia_001"
        }]
        zip_buf = create_test_zip(update_data, ["images/dacia.webp"])

        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tf:
            tf.write(zip_buf.getvalue())
            temp_path = tf.name

        try:
            importer = PubgZipImporter(temp_path)
            res = importer.execute_import(mode='update_existing')
            self.assertEqual(res['updated'], 1)
            self.assertEqual(res['created'], 0)

            item.refresh_from_db()
            self.assertEqual(item.value, Decimal("150.00"))
            self.assertEqual(item.rarity, "epic")
            self.assertEqual(item.quality, "Special")
            self.assertEqual(item.item_type, "vehicle")

        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_validation_rejects_non_pubg_game(self):
        """Strict requirement: Game must be PUBG. CS2 or other games must fail validation."""
        items = [{
            "game": "CS2",
            "name": "AK-47 | Redline",
            "price": 50.00,
            "image": "images/redline.webp"
        }]
        zip_buf = create_test_zip(items, ["images/redline.webp"])

        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tf:
            tf.write(zip_buf.getvalue())
            temp_path = tf.name

        try:
            importer = PubgZipImporter(temp_path)
            inspection = importer.validate_and_inspect()
            self.assertFalse(inspection['is_valid'])
            self.assertEqual(inspection['error_items'], 1)
            self.assertIn("Игра должна быть строго 'PUBG'", inspection['errors_list'][0])

            # Ensure execution is blocked and raises exception
            with self.assertRaises(PubgImportValidationError):
                importer.execute_import()

            # Ensure 0 items were inserted
            self.assertFalse(Item.objects.filter(name="AK-47 | Redline").exists())

        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_validation_rejects_missing_image_in_zip(self):
        """Validation fails if an item references an image that is not in the ZIP."""
        items = [{
            "game": "PUBG",
            "name": "Missing Image Pan",
            "price": 30.00,
            "image": "images/non_existent.webp"
        }]
        # Create ZIP without images/non_existent.webp
        zip_buf = create_test_zip(items, [])

        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tf:
            tf.write(zip_buf.getvalue())
            temp_path = tf.name

        try:
            importer = PubgZipImporter(temp_path)
            inspection = importer.validate_and_inspect()
            self.assertFalse(inspection['is_valid'])
            self.assertIn("не найдено внутри ZIP-архива", inspection['errors_list'][0])

            with self.assertRaises(PubgImportValidationError):
                importer.execute_import()

        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_missing_items_json_raises_error(self):
        """ZIP without items.json raises PubgImportValidationError."""
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, 'w') as zf:
            zf.writestr('some_file.txt', 'hello')
        zip_buf.seek(0)

        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tf:
            tf.write(zip_buf.getvalue())
            temp_path = tf.name

        try:
            with self.assertRaises(PubgImportValidationError):
                PubgZipImporter(temp_path).validate_and_inspect()
        finally:
            Path(temp_path).unlink(missing_ok=True)


class PubgImportAdminViewsTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        # Admin user with can_add_items
        self.admin_user = User.objects.create_superuser(
            username="pubg_admin",
            email="admin@neondrop.com",
            password="secretpassword"
        )
        self.client.force_login(self.admin_user)

    def test_admin_pubg_import_view_get(self):
        """Verify GET request to admin_pubg_import renders upload step."""
        url = reverse('admin_pubg_import')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('ИМПОРТ PUBG ПРЕДМЕТОВ', response.content.decode('utf-8'))
        self.assertIn('Загрузка архива с предметами', response.content.decode('utf-8'))

    def test_admin_pubg_import_preview_and_execute_post(self):
        """Verify POST upload creates preview and subsequent execution imports items."""
        items = [{
            "game": "PUBG",
            "name": "Test Pan Neon",
            "price": 99.00,
            "rarity": "Epic",
            "image": "images/test_pan.webp",
            "source_id": "pan_neon_99"
        }]
        zip_buf = create_test_zip(items, ["images/test_pan.webp"])
        uploaded = SimpleUploadedFile("items_import.zip", zip_buf.getvalue(), content_type="application/zip")

        url = reverse('admin_pubg_import')

        # 1. POST preview
        response = self.client.post(url, {'action': 'preview', 'zip_file': uploaded})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn('Результаты проверки архива', content)
        self.assertIn('Test Pan Neon', content)
        self.assertIn('token', response.context)
        token = response.context['token']

        # 2. POST execute
        exec_response = self.client.post(url, {
            'action': 'execute',
            'token': token,
            'mode': 'add_only'
        })
        self.assertEqual(exec_response.status_code, 200)
        exec_content = exec_response.content.decode('utf-8')
        self.assertIn('ИМПОРТ ЗАВЕРШЁН', exec_content)
        self.assertIn('Новых', exec_content)

        # Check DB
        self.assertTrue(Item.objects.filter(source_id="pan_neon_99").exists())

    def test_admin_pubg_import_streaming_view(self):
        """Verify streaming NDJSON endpoint emits progress lines and complete summary."""
        items = [{
            "game": "PUBG",
            "name": "Streaming Test Skin",
            "price": 10.00,
            "image": "images/stream.webp",
            "source_id": "stream_test_01"
        }]
        zip_buf = create_test_zip(items, ["images/stream.webp"])
        uploaded = SimpleUploadedFile("items.zip", zip_buf.getvalue(), content_type="application/zip")

        # Step 1: Upload to get token
        resp1 = self.client.post(reverse('admin_pubg_import'), {'action': 'preview', 'zip_file': uploaded})
        token = resp1.context['token']

        # Step 2: Call stream endpoint
        stream_url = reverse('admin_pubg_import_stream')
        stream_resp = self.client.post(
            stream_url,
            data=json.dumps({'token': token, 'mode': 'add_only'}),
            content_type='application/json'
        )
        self.assertEqual(stream_resp.status_code, 200)
        self.assertIn('application/x-ndjson', stream_resp['Content-Type'])

        # Read streaming content
        stream_content = b"".join(stream_resp.streaming_content).decode('utf-8')
        self.assertIn('"event": "progress"', stream_content)
        self.assertIn('"event": "complete"', stream_content)
        self.assertIn('"created": 1', stream_content)

    def test_non_staff_forbidden(self):
        """Verify non-staff / unauthenticated user is forbidden or redirected."""
        regular_user = User.objects.create_user(username="regular", password="pwd")
        self.client.force_login(regular_user)
        response = self.client.get(reverse('admin_pubg_import'))
        # Should redirect to admin login or return 302/403
        self.assertIn(response.status_code, [302, 403])

    def test_import_with_id_field(self):
        """Verify items.json entries using 'id' field instead of 'source_id' are handled properly."""
        items = [{
            "game": "PUBG",
            "id": "pubg_item_custom_999",
            "name": "Pan of Justice",
            "price": 500.00,
            "rarity": "Mythic",
            "quality": "Elite",
            "type": "melee",
            "image": "images/justice_pan.webp"
        }]
        zip_buf = create_test_zip(items, ["images/justice_pan.webp"])

        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tf:
            tf.write(zip_buf.getvalue())
            temp_path = tf.name

        try:
            importer = PubgZipImporter(temp_path)
            res = importer.execute_import(mode='add_only')
            self.assertEqual(res['created'], 1)

            item = Item.objects.filter(source_id="pubg_item_custom_999").first()
            self.assertIsNotNone(item)
            self.assertEqual(item.name, "Pan of Justice")
            self.assertEqual(item.rarity, "mythic")
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_backup_restore_rejection_of_items_zip(self):
        """Verify that uploading items_import.zip to backup/restore gives clear guidance to use PUBG importer."""
        from cases.backup_restore_service import inspect_backup_zip, BackupRestoreError
        items = [{
            "game": "PUBG",
            "name": "Test Item",
            "price": 10.0,
            "image": "images/test.webp"
        }]
        zip_buf = create_test_zip(items, ["images/test.webp"])

        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tf:
            tf.write(zip_buf.getvalue())
            temp_path = tf.name

        try:
            with self.assertRaises(BackupRestoreError) as cm:
                inspect_backup_zip(temp_path)
            self.assertIn("Импорт PUBG предметов", str(cm.exception))
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_session_lifecycle_and_clean_storage(self):
        """Verify PubgImportSession lifecycle: created on preview, cleaned on success, idempotent."""
        items = [{
            "game": "PUBG",
            "name": "M249 | Jungle Camo",
            "price": 120.00,
            "rarity": "Rare",
            "image": "images/m249.webp",
            "source_id": "m249_lifecycle_01"
        }]
        zip_buf = create_test_zip(items, ["images/m249.webp"])
        uploaded = SimpleUploadedFile("m249_import.zip", zip_buf.getvalue(), content_type="application/zip")

        url = reverse('admin_pubg_import')

        # 1. Preview step
        resp = self.client.post(url, {'action': 'preview', 'zip_file': uploaded})
        self.assertEqual(resp.status_code, 200)
        token = resp.context['token']

        session = PubgImportSession.objects.filter(session_id=token).first()
        self.assertIsNotNone(session)
        self.assertEqual(session.status, 'preview')
        self.assertEqual(session.total_items, 1)
        self.assertEqual(session.new_items_count, 1)
        self.assertTrue(Path(session.zip_path).exists())

        # 2. Confirm / Execute step
        exec_resp = self.client.post(url, {'action': 'execute', 'token': token, 'mode': 'add_only'})
        self.assertEqual(exec_resp.status_code, 200)

        session.refresh_from_db()
        self.assertEqual(session.status, 'completed')
        self.assertEqual(session.summary_data.get('created'), 1)
        # Storage file must be deleted on success
        self.assertFalse(Path(session.zip_path).exists(), "ZIP must be cleaned up on successful completion!")

        # 3. Idempotency test: submitting again must not fail
        repeat_resp = self.client.post(url, {'action': 'execute', 'token': token, 'mode': 'add_only'})
        self.assertEqual(repeat_resp.status_code, 200)
        self.assertIn('ИМПОРТ ЗАВЕРШЁН', repeat_resp.content.decode('utf-8'))

    def test_missing_image_does_not_abort_transaction(self):
        """Verify that an item with missing/corrupted image during extraction does not rollback valid items."""
        items = [
            {
                "game": "PUBG",
                "name": "Item With Corrupted Image",
                "price": 50.00,
                "rarity": "Common",
                "image": "images/corrupted_img.webp",
                "source_id": "corrupted_img_item_01"
            },
            {
                "game": "PUBG",
                "name": "Item With Valid Image",
                "price": 80.00,
                "rarity": "Rare",
                "image": "images/valid_img.webp",
                "source_id": "valid_img_item_02"
            }
        ]
        # Both images exist in archive namelist
        zip_buf = create_test_zip(items, ["images/corrupted_img.webp", "images/valid_img.webp"])

        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tf:
            tf.write(zip_buf.getvalue())
            temp_path = tf.name

        try:
            importer = PubgZipImporter(temp_path)

            orig_read = zipfile.ZipFile.read

            def mock_read(self_zf, name, *args, **kwargs):
                if "corrupted_img" in str(name):
                    raise zipfile.BadZipFile("CRC error or corrupted compressed data in image")
                return orig_read(self_zf, name, *args, **kwargs)

            with patch.object(zipfile.ZipFile, 'read', side_effect=mock_read, autospec=True):
                res = importer.execute_import(mode='add_only')

            # Both items should be created in DB despite extraction error on item 1!
            self.assertEqual(res['created'], 2)
            self.assertEqual(res['errors'], 1)  # 1 image error tracked
            self.assertEqual(res['images_saved'], 1)

            it1 = Item.objects.filter(source_id="corrupted_img_item_01").first()
            it2 = Item.objects.filter(source_id="valid_img_item_02").first()
            self.assertIsNotNone(it1, "Item 1 must be created even with image error!")
            self.assertIsNotNone(it2, "Item 2 must be created with image!")
            self.assertTrue(bool(it2.image))
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_reimport_same_zip_prevents_duplicates(self):
        """Verify re-importing the exact same ZIP in add_only mode creates 0 duplicates."""
        items = [
            {"game": "PUBG", "name": "Item Alpha", "price": 10.0, "source_id": "alpha_01", "image": "images/a.webp"},
            {"game": "PUBG", "name": "Item Beta", "price": 20.0, "source_id": "beta_02", "image": "images/b.webp"},
        ]
        zip_buf = create_test_zip(items, ["images/a.webp", "images/b.webp"])
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tf:
            tf.write(zip_buf.getvalue())
            temp_path = tf.name

        try:
            importer1 = PubgZipImporter(temp_path)
            res1 = importer1.execute_import(mode='add_only')
            self.assertEqual(res1['created'], 2)
            self.assertEqual(res1['skipped'], 0)

            # Second import with same archive
            importer2 = PubgZipImporter(temp_path)
            res2 = importer2.execute_import(mode='add_only')
            self.assertEqual(res2['created'], 0, "No duplicate items should be created on re-import!")
            self.assertEqual(res2['skipped'], 2, "Both items should be skipped as existing!")
            self.assertEqual(Item.objects.filter(source_id__in=["alpha_01", "beta_02"]).count(), 2)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_zip_with_mix_of_new_and_existing(self):
        """Verify archive with both new and existing items handles them according to mode."""
        # Pre-create 1 item in DB
        Item.objects.create(
            name="Existing Kar98k",
            game="PUBG",
            value=Decimal("150.00"),
            source_id="kar98_exist_01"
        )

        items = [
            {"game": "PUBG", "name": "Existing Kar98k", "price": 199.00, "source_id": "kar98_exist_01", "image": "images/k.webp"},
            {"game": "PUBG", "name": "New AWM", "price": 300.00, "source_id": "awm_new_02", "image": "images/awm.webp"},
        ]
        zip_buf = create_test_zip(items, ["images/k.webp", "images/awm.webp"])
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tf:
            tf.write(zip_buf.getvalue())
            temp_path = tf.name

        try:
            # Mode: update_existing
            importer = PubgZipImporter(temp_path)
            res = importer.execute_import(mode='update_existing')
            self.assertEqual(res['created'], 1)
            self.assertEqual(res['updated'], 1)

            updated_kar = Item.objects.get(source_id="kar98_exist_01")
            self.assertEqual(updated_kar.value, Decimal("199.00"))
            self.assertTrue(Item.objects.filter(source_id="awm_new_02").exists())
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_damaged_zip_handled_gracefully(self):
        """Verify corrupted ZIP file returns validation error and doesn't crash the server."""
        corrupted_bytes = b"NOT_A_VALID_ZIP_CONTENT_CORRUPTED"
        uploaded = SimpleUploadedFile("broken.zip", corrupted_bytes, content_type="application/zip")
        url = reverse('admin_pubg_import')

        resp = self.client.post(url, {'action': 'preview', 'zip_file': uploaded})
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Ошибка валидации', resp.content.decode('utf-8'))

    def test_streaming_live_subcounters(self):
        """Verify NDJSON streaming returns detailed subcounters in progress events."""
        items = [
            {"game": "PUBG", "name": "Stream Item 1", "price": 10.0, "source_id": "str_01", "image": "images/s1.webp"},
            {"game": "PUBG", "name": "Stream Item 2", "price": 20.0, "source_id": "str_02", "image": "images/s2.webp"},
        ]
        zip_buf = create_test_zip(items, ["images/s1.webp", "images/s2.webp"])
        uploaded = SimpleUploadedFile("stream_subcounters.zip", zip_buf.getvalue(), content_type="application/zip")

        preview_resp = self.client.post(reverse('admin_pubg_import'), {'action': 'preview', 'zip_file': uploaded})
        token = preview_resp.context['token']

        stream_url = reverse('admin_pubg_import_stream')
        stream_resp = self.client.post(
            stream_url,
            data=json.dumps({'token': token, 'mode': 'add_only'}),
            content_type='application/json'
        )
        self.assertEqual(stream_resp.status_code, 200)

        lines = [line.strip() for line in b"".join(stream_resp.streaming_content).decode('utf-8').split('\n') if line.strip()]
        progress_events = [json.loads(line) for line in lines if '"event": "progress"' in line]
        self.assertTrue(len(progress_events) >= 2)
        # Check subcounters are present in progress events
        for p in progress_events:
            self.assertIn('created', p)
            self.assertIn('updated', p)
            self.assertIn('skipped', p)
            self.assertIn('errors', p)


class PubgExistingItemLogicTestCase(TestCase):
    def setUp(self):
        Item.objects.all().delete()

    def test_test1_no_item_in_db_returns_new(self):
        """TEST 1: In DB there is no item. ZIP contains this item. Result: NEW."""
        item_data = {
            "name": "M416 | Digital Camo",
            "game": "PUBG",
            "source_id": "item_test_001",
            "price": 150.0,
            "image": "images/item_01.webp"
        }
        item, match_type, reason = PubgZipImporter.find_existing_item(item_data)
        self.assertIsNone(item)
        self.assertIsNone(match_type)
        self.assertIsNone(reason)

    def test_test2_exact_source_id_in_db_returns_existing(self):
        """TEST 2: In DB there is an item with the exact same source_id. Result: EXISTING."""
        db_item = Item.objects.create(
            name="M416 | Digital Camo",
            game="PUBG",
            value=Decimal("150.00"),
            source_id="item_test_002"
        )
        item_data = {
            "name": "M416 | Digital Camo",
            "game": "PUBG",
            "source_id": "item_test_002",
            "price": 150.0,
            "image": "images/item_02.webp"
        }
        matched_item, match_type, reason = PubgZipImporter.find_existing_item(item_data)
        self.assertIsNotNone(matched_item)
        self.assertEqual(matched_item.id, db_item.id)
        self.assertEqual(match_type, 'source_id')
        self.assertEqual(reason, 'Совпало по source_id')

    def test_test3_same_name_different_source_id_or_url_returns_new(self):
        """TEST 3: In DB there is an item with the same name, but different source_id/source_url. Result: NEW!"""
        # DB item has source_id="src_db_001" and source_url="https://market.com/items/001"
        Item.objects.create(
            name="AKM | Wasteland Rebel",
            game="PUBG",
            value=Decimal("200.00"),
            source_id="src_db_001",
            source_url="https://market.com/items/001"
        )

        # Incoming item has same name, but DIFFERENT source_id
        item_data_diff_source_id = {
            "name": "AKM | Wasteland Rebel",
            "game": "PUBG",
            "source_id": "src_diff_999",
            "price": 200.0,
            "image": "images/item_03.webp"
        }
        matched_item, match_type, reason = PubgZipImporter.find_existing_item(item_data_diff_source_id)
        self.assertIsNone(matched_item, "Must NOT match by name if source_id is provided and differs!")
        self.assertIsNone(match_type)

        # Incoming item has same name, no source_id, but DIFFERENT source_url
        item_data_diff_source_url = {
            "name": "AKM | Wasteland Rebel",
            "game": "PUBG",
            "source_url": "https://othermarket.com/items/999",
            "price": 200.0,
            "image": "images/item_03.webp"
        }
        matched_item, match_type, reason = PubgZipImporter.find_existing_item(item_data_diff_source_url)
        self.assertIsNone(matched_item, "Must NOT match by name if source_url is provided and differs!")
        self.assertIsNone(match_type)

    def test_test4_similar_name_no_fuzzy_returns_new(self):
        """TEST 4: In DB there is a similar name. Result: NEW, no fuzzy matching."""
        Item.objects.create(
            name="AKM | Wasteland Rebel",
            game="PUBG",
            value=Decimal("200.00")
        )
        Item.objects.create(
            name="Item A",
            game="PUBG",
            value=Decimal("50.00")
        )

        # "AKM | Wasteland Rebel (Field-Tested)" vs "AKM | Wasteland Rebel"
        item_data_1 = {
            "name": "AKM | Wasteland Rebel (Field-Tested)",
            "game": "PUBG",
            "price": 200.0,
            "image": "images/item_04a.webp"
        }
        matched_item, match_type, reason = PubgZipImporter.find_existing_item(item_data_1)
        self.assertIsNone(matched_item, "AKM | Wasteland Rebel (Field-Tested) must NOT match AKM | Wasteland Rebel!")

        # "Item A 2" vs "Item A"
        item_data_2 = {
            "name": "Item A 2",
            "game": "PUBG",
            "price": 50.0,
            "image": "images/item_04b.webp"
        }
        matched_item, match_type, reason = PubgZipImporter.find_existing_item(item_data_2)
        self.assertIsNone(matched_item, "Item A 2 must NOT match Item A!")

    def test_test5_zip_with_27_new_items_preview_shows_new_27_existing_0(self):
        """TEST 5: ZIP contains 27 new PUBG items. Preview must show: NEW = 27, EXISTING = 0."""
        # Ensure DB has some other items
        Item.objects.create(name="Existing DB Item 1", game="PUBG", value=Decimal("10.00"))
        Item.objects.create(name="Existing DB Item 2", game="PUBG", value=Decimal("20.00"))

        # Generate 27 distinct new items
        items_27 = []
        image_files = []
        for i in range(1, 28):
            img_path = f"images/item_{i:04d}.webp"
            items_27.append({
                "game": "PUBG",
                "name": f"PUBG Weapon Skin #{i:03d}",
                "price": 100.0 + i,
                "rarity": "Rare",
                "quality": "Refined",
                "type": "weapon",
                "source_id": f"pubg_unique_ext_{i:04d}",
                "source_url": f"https://pubg.game/item/{i}",
                "image": img_path
            })
            image_files.append(img_path)

        zip_buf = create_test_zip(items_27, image_files)
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tf:
            tf.write(zip_buf.getvalue())
            temp_path = tf.name

        try:
            importer = PubgZipImporter(temp_path)
            inspection = importer.inspect_and_validate()
            self.assertTrue(inspection['is_valid'])
            self.assertEqual(inspection['total_items'], 27)
            self.assertEqual(inspection['new_items'], 27, "All 27 items must be NEW!")
            self.assertEqual(inspection['existing_items'], 0, "EXISTING must be 0!")
            self.assertEqual(inspection['error_items'], 0)

            # Check every preview item has status 'new' and display_status 'NEW'
            for it in inspection['preview_items']:
                self.assertEqual(it['status'], 'new')
                self.assertEqual(it['display_status'], 'NEW')
                self.assertIsNone(it['existing_id'])
                self.assertIsNone(it['matched_by'])
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_reverse_matching_existing_item_detected_correctly(self):
        """Verify reverse: if item REALLY exists in DB, it is correctly identified as EXISTING."""
        # 1. Match by source_id
        db_item_1 = Item.objects.create(
            name="Pan | Golden Dragon",
            game="PUBG",
            value=Decimal("500.00"),
            source_id="src_dragon_1"
        )
        matched, match_type, reason = PubgZipImporter.find_existing_item({"source_id": "src_dragon_1"})
        self.assertEqual(matched.id, db_item_1.id)
        self.assertEqual(match_type, 'source_id')
        self.assertEqual(reason, 'Совпало по source_id')

        # 2. Match by source_url (no source_id)
        db_item_2 = Item.objects.create(
            name="Helmet | Level 3",
            game="PUBG",
            value=Decimal("300.00"),
            source_url="https://pubg.market/item/helmet3"
        )
        matched, match_type, reason = PubgZipImporter.find_existing_item({"source_url": "https://pubg.market/item/helmet3/"})
        self.assertEqual(matched.id, db_item_2.id)
        self.assertEqual(match_type, 'source_url')
        self.assertEqual(reason, 'Совпало по source_url')

        # 3. Match by game + exact normalized name (no source_id, no source_url)
        db_item_3 = Item.objects.create(
            name="Beryl M762 | Cyberpunk",
            game="PUBG",
            value=Decimal("250.00")
        )
        matched, match_type, reason = PubgZipImporter.find_existing_item({
            "name": "  Beryl   M762 |  Cyberpunk  ",
            "game": "PUBG"
        })
        self.assertEqual(matched.id, db_item_3.id)
        self.assertEqual(match_type, 'name_game')
        self.assertEqual(reason, 'Совпало по game + name')
