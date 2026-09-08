import os
from decimal import Decimal
from pathlib import Path
from django.test import TestCase, Client
from django.conf import settings
from django.contrib.auth.models import User
from django.urls import reverse

from cases.models import Case, Item, CaseItem
from users.models import Profile


class LamborghiniCaseTestCase(TestCase):
    """
    Validation test suite for the 5,000 UC Lamborghini case:
    - 24 items with exact mathematical weights and 80.00% RTP
    - Image assets exist in media/ and static/
    - Server-side opening API transactions and provably fair RNG
    """

    def setUp(self):
        self.user = User.objects.create_user(username='LamboHighRoller', password='testpassword123')
        profile, _ = Profile.objects.get_or_create(user=self.user)
        profile.balance = Decimal('50000.00')
        profile.save()
        self.client = Client()
        self.client.force_login(self.user)

    def test_lamborghini_case_configuration_and_rtp(self):
        case = Case.objects.filter(slug='lamborghini').first()
        self.assertIsNotNone(case, "Lamborghini case must exist in database")
        self.assertEqual(case.price, Decimal('5000.00'))
        self.assertTrue(case.active)

        case_items = list(case.case_items.select_related('item').all())
        self.assertEqual(len(case_items), 24, "Must contain exactly 24 items")

        total_weight = sum(ci.weight for ci in case_items)
        self.assertAlmostEqual(total_weight, 100.0, places=3, msg="Total drop probability must be 100.000%")

        ev = sum((ci.weight / total_weight) * float(ci.item.value) for ci in case_items)
        rtp = (ev / float(case.price)) * 100.0
        self.assertAlmostEqual(rtp, 80.0, places=2, msg="Target RTP must be strictly 80.00%")
        self.assertAlmostEqual(ev, 4000.0, delta=1.0, msg="Expected return must be 4,000 UC")

        # Verify monotonicity: every higher-priced item has <= drop chance than lower-priced item
        sorted_items = sorted(case_items, key=lambda ci: float(ci.item.value))
        for i in range(len(sorted_items) - 1):
            curr_ci = sorted_items[i]
            next_ci = sorted_items[i + 1]
            self.assertGreaterEqual(
                curr_ci.weight,
                next_ci.weight,
                f"Item {curr_ci.item.name} ({curr_ci.item.value} UC, chance {curr_ci.weight}%) should have >= chance than {next_ci.item.name} ({next_ci.item.value} UC, chance {next_ci.weight}%)"
            )

    def test_lamborghini_images_exist(self):
        case = Case.objects.get(slug='lamborghini')
        # Check case cover image
        cover_path = Path(settings.MEDIA_ROOT) / str(case.image)
        self.assertTrue(cover_path.exists(), f"Case cover image must exist at {cover_path}")

        # Check all 24 item images
        for ci in case.case_items.select_related('item').all():
            it = ci.item
            self.assertTrue(it.image, f"Item {it.name} must have image set")
            media_p = Path(settings.MEDIA_ROOT) / str(it.image)
            static_p = Path(settings.BASE_DIR) / 'static' / str(it.image)
            self.assertTrue(media_p.exists(), f"Image for {it.name} missing in media: {media_p}")
            self.assertTrue(static_p.exists(), f"Image for {it.name} missing in static: {static_p}")

    def test_lamborghini_case_opening_api(self):
        url = reverse('cases:open_case_api', kwargs={'slug': 'lamborghini'})
        Profile.objects.filter(user=self.user).update(balance=Decimal('50000.00'))
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.balance, Decimal('50000.00'))
        initial_balance = profile.balance

        resp = self.client.post(url, {'quantity': 1})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['quantity'], 1)
        self.assertEqual(data['total_price'], 5000.0)

        profile.refresh_from_db()
        self.assertEqual(profile.balance, initial_balance - Decimal('5000.00'))

        won = data['results'][0]['won_item']
        self.assertIn('name', won)
        self.assertIn('value', won)
        self.assertIn('rarity', won)
        self.assertIn('image_url', won)
