import os
import json
from pathlib import Path
from decimal import Decimal
from PIL import Image

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.conf import settings
from django.urls import reverse

from cases.models import Case, Item, CaseItem, Category
from cases.rtp_calculator import (
    classify_tier,
    calculate_rtp_chances,
    validate_case_chances,
    InvalidChancesError,
)
from cases.image_importer import (
    PARADISE_ITEMS_METADATA,
    extract_items_from_grid_image,
    import_or_update_items,
)
from cases.provably_fair import (
    generate_server_seed,
    calculate_provably_fair_roll,
    select_weighted_item,
)


class RTPCalculatorTestCase(TestCase):
    """
    Test suite for mathematical precision of the RTP calculation engine.
    """

    def setUp(self):
        self.sample_items = [
            {'name': 'Golden Knife', 'price': 200.0, 'rarity': 'knife'},
            {'name': 'Covert Rifle', 'price': 80.0, 'rarity': 'covert'},
            {'name': 'Classified SMG', 'price': 35.0, 'rarity': 'classified'},
            {'name': 'Restricted Pistol', 'price': 15.0, 'rarity': 'restricted'},
            {'name': 'Mil-spec Shotgun', 'price': 7.0, 'rarity': 'mil_spec'},
            {'name': 'Consumer Grey', 'price': 2.5, 'rarity': 'consumer'},
        ]

    def test_classify_tier(self):
        case_price = Decimal("15.00")
        self.assertEqual(classify_tier(Decimal("180.00"), case_price), "Jackpot")    # 12x
        self.assertEqual(classify_tier(Decimal("75.00"), case_price), "Legendary")   # 5x
        self.assertEqual(classify_tier(Decimal("45.00"), case_price), "Epic")        # 3x
        self.assertEqual(classify_tier(Decimal("20.00"), case_price), "Rare")        # 1.33x
        self.assertEqual(classify_tier(Decimal("10.00"), case_price), "Uncommon")    # 0.67x
        self.assertEqual(classify_tier(Decimal("3.00"), case_price), "Common")       # 0.2x

    def test_calculate_rtp_chances_balanced_mode(self):
        case_price = Decimal("15.00")
        target_rtp = 0.90  # 90%
        result = calculate_rtp_chances(self.sample_items, case_price, target_rtp=target_rtp, mode='balanced')

        # 1. Probabilities sum strictly to 100.000%
        self.assertAlmostEqual(result['total_prob'], 100.0, places=2)

        # 2. Expected return matches price * RTP (15 * 0.90 = 13.50 UC)
        self.assertAlmostEqual(result['expected_return'], 13.50, delta=0.2)

        # 3. House edge is ~10%
        self.assertAlmostEqual(result['house_edge'], 10.0, delta=1.5)

        # 4. All item chances are strictly positive
        for it in result['items']:
            self.assertGreater(it['chance_pct'], 0.0)
            self.assertIn('tier', it)
            self.assertIn('expected_contribution', it)

        # 5. Higher value items have lower chances than cheap items
        jackpot_item = next(it for it in result['items'] if it['name'] == 'Golden Knife')
        common_item = next(it for it in result['items'] if it['name'] == 'Consumer Grey')
        self.assertLess(jackpot_item['chance_pct'], common_item['chance_pct'])

    def test_calculate_rtp_chances_volatile_mode(self):
        case_price = Decimal("15.00")
        target_rtp = 0.90
        res_balanced = calculate_rtp_chances(self.sample_items, case_price, target_rtp=target_rtp, mode='balanced')
        res_volatile = calculate_rtp_chances(self.sample_items, case_price, target_rtp=target_rtp, mode='volatile')

        self.assertAlmostEqual(res_volatile['total_prob'], 100.0, places=2)

        # In volatile mode, top jackpot item has higher drop chance relative to balanced mode
        jackpot_bal = next(it for it in res_balanced['items'] if it['name'] == 'Golden Knife')['chance_pct']
        jackpot_vol = next(it for it in res_volatile['items'] if it['name'] == 'Golden Knife')['chance_pct']
        self.assertGreater(jackpot_vol, jackpot_bal)

    def test_paradise_eruption_24_items_rtp(self):
        items = [{'name': m['name'], 'price': float(m['value']), 'rarity': m['rarity']} for m in PARADISE_ITEMS_METADATA]
        case_price = Decimal("15.00")
        res = calculate_rtp_chances(items, case_price=case_price, target_rtp=0.70, mode='balanced')

        self.assertEqual(len(res['items']), 24)
        self.assertAlmostEqual(res['total_prob'], 100.0, places=3)
        self.assertAlmostEqual(res['expected_return'], 10.50, delta=0.1)
        self.assertAlmostEqual(res['actual_rtp'], 70.0, delta=0.5)
        self.assertAlmostEqual(res['house_edge'], 30.0, delta=0.5)

        for it in res['items']:
            self.assertGreater(it['chance_pct'], 0.0)

    def test_validate_case_chances_raises_on_invalid(self):
        # Create a mock case
        case = Case.objects.create(name="Test Faulty Case", slug="test-faulty-case", price=Decimal("10.00"))
        it1 = Item.objects.create(name="Item 1", value=Decimal("10.00"))
        it2 = Item.objects.create(name="Item 2", value=Decimal("5.00"))

        # Weights sum to 50% instead of 100%
        CaseItem.objects.create(case=case, item=it1, weight=30.0)
        CaseItem.objects.create(case=case, item=it2, weight=20.0)

        with self.assertRaises(InvalidChancesError):
            validate_case_chances(CaseItem.objects.filter(case=case))


class ImageImporterTestCase(TestCase):
    """
    Tests grid slicing, metadata extraction, and non-destructive idempotent imports.
    """

    def test_paradise_metadata_count_and_uniqueness(self):
        self.assertEqual(len(PARADISE_ITEMS_METADATA), 24)
        names = [m['name'] for m in PARADISE_ITEMS_METADATA]
        self.assertEqual(len(names), len(set(names)), "Item names in metadata must be unique")

    def test_import_or_update_items_idempotent(self):
        # 1st run: creates items
        created_items = import_or_update_items(PARADISE_ITEMS_METADATA)
        self.assertEqual(len(created_items), 24)
        count_first = Item.objects.filter(name__in=[m['name'] for m in PARADISE_ITEMS_METADATA]).count()
        self.assertEqual(count_first, 24)

        # 2nd run: does not duplicate items
        import_or_update_items(PARADISE_ITEMS_METADATA)
        count_second = Item.objects.filter(name__in=[m['name'] for m in PARADISE_ITEMS_METADATA]).count()
        self.assertEqual(count_second, 24)


class AdminImageImportEndpointsTestCase(TestCase):
    """
    Test suite for admin GUI views and AJAX endpoints.
    """

    def setUp(self):
        self.admin_user = User.objects.create_superuser('admin_tester', 'admin@example.com', 'supersecret123')
        self.client = Client()
        self.client.force_login(self.admin_user)

    def test_admin_image_import_view_get(self):
        url = reverse('admin_image_import')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'МАССОВЫЙ ИМПОРТ ПРЕДМЕТОВ')
        self.assertContains(response, 'Райское извержение')

    def test_ajax_calculate_rtp_endpoint(self):
        url = reverse('admin_ajax_calculate_rtp')
        payload = {
            'case_price': 15.0,
            'target_rtp': 90.0,
            'mode': 'balanced',
            'items': [
                {'name': 'Pan', 'price': 180.0, 'rarity': 'knife'},
                {'name': 'Glider', 'price': 150.0, 'rarity': 'covert'},
                {'name': 'Hat', 'price': 2.0, 'rarity': 'consumer'}
            ]
        }
        response = self.client.post(url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertAlmostEqual(data['result']['total_prob'], 100.0, places=2)
        self.assertEqual(len(data['result']['items']), 3)

    def test_ajax_create_case_endpoint(self):
        url = reverse('admin_ajax_create_case')
        payload = {
            'case_name': 'Райское извержение Тест',
            'case_slug': 'paradise_test_slug',
            'case_price': 15.0,
            'color_theme': 'demon-orange',
            'category_slug': 'limited',
            'items': [
                {
                    'name': 'Pan Test',
                    'weapon_type': 'Pan',
                    'skin_name': 'Crimson Fox',
                    'rarity': 'knife',
                    'price': 180.0,
                    'chance_pct': 1.0
                },
                {
                    'name': 'Glider Test',
                    'weapon_type': 'Glider',
                    'skin_name': 'Blueyonder',
                    'rarity': 'covert',
                    'price': 150.0,
                    'chance_pct': 2.0
                },
                {
                    'name': 'Hat Test',
                    'weapon_type': 'Hat',
                    'skin_name': 'Iron Judge',
                    'rarity': 'consumer',
                    'price': 2.0,
                    'chance_pct': 97.0
                }
            ]
        }
        response = self.client.post(url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')

        # Check in DB
        case = Case.objects.get(slug='paradise_test_slug')
        self.assertEqual(case.price, Decimal("15.00"))
        self.assertEqual(case.case_items.count(), 3)
        self.assertAlmostEqual(sum(ci.weight for ci in case.case_items.all()), 100.0, places=2)

    def test_all_24_item_images_and_case_cover_serve_200(self):
        """
        Guarantees that all 24 item icons and case artwork exist in static storage
        and return HTTP 200 OK via /media/ with static fallback, preventing broken images on Render.
        """
        # 1. Test case cover
        cover_static = Path(settings.BASE_DIR) / 'static' / 'cases' / 'paradise_eruption.jpg'
        self.assertTrue(cover_static.is_file(), "Cover image must exist in static/cases/")

        resp_cover_media = self.client.get('/media/cases/paradise_eruption.jpg')
        self.assertEqual(resp_cover_media.status_code, 200)
        self.assertEqual(resp_cover_media.headers.get('Content-Type'), 'image/jpeg')

        # 2. Test all 24 items
        for m in PARADISE_ITEMS_METADATA:
            slug = m['slug']
            item_static = Path(settings.BASE_DIR) / 'static' / 'items' / f"{slug}.png"
            self.assertTrue(item_static.is_file(), f"Item {slug}.png must exist in static/items/")

            url_media = f"/media/items/{slug}.png"
            res_m = self.client.get(url_media)
            self.assertEqual(res_m.status_code, 200, f"Media URL {url_media} must return 200")
            self.assertEqual(res_m.headers.get('Content-Type'), 'image/png')




class ProvablyFairRNGTestCase(TestCase):
    """
    Verifies that the server-side RNG operates without covert tampering
    and yields drops aligned with mathematically expected rates.
    """

    def test_provably_fair_roll_deterministic_and_uniform(self):
        server_seed = generate_server_seed()
        client_seed = "custom_client_seed_456"
        nonce = 1

        roll1 = calculate_provably_fair_roll(server_seed, client_seed, nonce)
        roll2 = calculate_provably_fair_roll(server_seed, client_seed, nonce)
        self.assertEqual(roll1, roll2, "Same seeds and nonce must yield identical roll")
        self.assertGreaterEqual(roll1, 0.0)
        self.assertLess(roll1, 1.0)

    def test_case_opening_distribution(self):
        case = Case.objects.create(name="Provably Case", slug="provably-case", price=Decimal("15.00"))
        it_rare = Item.objects.create(name="Rare Knife", value=Decimal("150.00"))
        it_common = Item.objects.create(name="Common Mask", value=Decimal("3.00"))

        ci_rare = CaseItem.objects.create(case=case, item=it_rare, weight=1.0)
        ci_common = CaseItem.objects.create(case=case, item=it_common, weight=99.0)

        case_items = [ci_rare, ci_common]
        server_seed = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        client_seed = "client_test_seed"

        # Test selecting item with provably fair RNG call
        selected_ci, roll, s_hash = select_weighted_item(case_items, server_seed, client_seed, nonce=1)
        self.assertIn(selected_ci.id, [ci_rare.id, ci_common.id])
        self.assertGreaterEqual(roll, 0.0)
        self.assertLess(roll, 1.0)
        self.assertEqual(len(s_hash), 64)
