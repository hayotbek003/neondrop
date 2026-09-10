import json
import zipfile
import tempfile
from decimal import Decimal
from pathlib import Path

from django.test import TestCase
from django.core.management import call_command
from django.conf import settings

from cases.models import Case, Item, CaseItem


class CustomCasesImportCommandTestCase(TestCase):
    def setUp(self):
        # Create a small sample ZIP for testing
        self.test_cases_data = [
            {
                "name": "Test Supercar Case",
                "price_uc": 10000,
                "target_rtp_percent": 80,
                "image": "images/test_case.jpg",
                "items": [
                    {
                        "name": "Test Supercar Case — Item 01",
                        "price_uc": 100,
                        "rarity": "Common",
                        "chance_percent": 50.0,
                        "image": None
                    },
                    {
                        "name": "Test Supercar Case — Item 02",
                        "price_uc": 500,
                        "rarity": "Rare",
                        "chance_percent": 25.0,
                        "image": None
                    },
                    {
                        "name": "Test Supercar Case — Item 13",
                        "price_uc": 25000,
                        "rarity": "Legendary",
                        "chance_percent": 0.0,
                        "image": None
                    },
                    {
                        "name": "Test Supercar Case — Item 14",
                        "price_uc": 45000,
                        "rarity": "Legendary",
                        "chance_percent": 0.0,
                        "image": None
                    }
                ]
            }
        ]

        self.temp_dir = tempfile.TemporaryDirectory()
        self.zip_path = Path(self.temp_dir.name) / "test_cases.zip"
        
        # 1x1 dummy image
        dummy_jpg = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' \",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9'

        with zipfile.ZipFile(self.zip_path, 'w') as zf:
            zf.writestr('cases.json', json.dumps(self.test_cases_data, ensure_ascii=False))
            zf.writestr('images/test_case.jpg', dummy_jpg)

    def tearDown(self):
        self.temp_dir.cleanup()
        # Clean up any created test images
        for base in [settings.BASE_DIR / 'media' / 'cases', settings.BASE_DIR / 'static' / 'cases']:
            for name in ['test-supercar-case.jpg', 'test_supercar_case.jpg']:
                f = base / name
                if f.exists():
                    try:
                        f.unlink()
                    except Exception:
                        pass

    def test_import_cases_command_as_is(self):
        """Verify import_custom_cases_zip creates case, items, CaseItems and image."""
        call_command('import_custom_cases_zip', str(self.zip_path), '--chances-mode=as_is')

        case = Case.objects.filter(slug='test-supercar-case').first()
        self.assertIsNotNone(case)
        self.assertEqual(case.price, Decimal("10000.00"))
        self.assertEqual(case.case_items.count(), 4)

        # Check item properties
        item1 = Item.objects.filter(name="Test Supercar Case — Item 01").first()
        self.assertIsNotNone(item1)
        self.assertEqual(item1.value, Decimal("100.00"))
        self.assertEqual(item1.rarity, "common")
        self.assertEqual(item1.game, "PUBG")

        # Check CaseItem weights
        ci1 = CaseItem.objects.get(case=case, item=item1)
        self.assertEqual(ci1.weight, 50.0)

        # Check re-running prevents duplicates
        call_command('import_custom_cases_zip', str(self.zip_path), '--chances-mode=as_is')
        self.assertEqual(Case.objects.filter(slug='test-supercar-case').count(), 1)
        self.assertEqual(Item.objects.filter(name="Test Supercar Case — Item 01").count(), 1)
        self.assertEqual(case.case_items.count(), 4)

    def test_import_cases_command_solve_rtp(self):
        """Verify solve_rtp balances items 13 and 14 so sum is 100%."""
        call_command('import_custom_cases_zip', str(self.zip_path), '--chances-mode=solve_rtp')

        case = Case.objects.get(slug='test-supercar-case')
        cis = list(case.case_items.select_related('item').all())
        tot_w = sum(ci.weight for ci in cis)
        self.assertAlmostEqual(tot_w, 100.0, places=2)
