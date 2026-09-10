import io
import json
import zipfile
import tempfile
from decimal import Decimal
from pathlib import Path

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from cases.models import Item
from users.models import AdminPermissionProfile
from cases.pubg_importer_service import (
    PubgZipImporter,
    PubgImportValidationError,
    normalize_url,
    map_pubg_rarity,
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
        match_obj, match_type = PubgZipImporter.find_existing_item({
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
        match_obj2, match_type2 = PubgZipImporter.find_existing_item({
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
        match_obj3, match_type3 = PubgZipImporter.find_existing_item({
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
        self.assertIn('ИМПОРТ PUBG ПРЕДМЕТОВ ИЗ ZIP', response.content.decode('utf-8'))
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
        self.assertIn('Новых предметов', exec_content)

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
