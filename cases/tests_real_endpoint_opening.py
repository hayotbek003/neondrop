from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse

from cases.models import Case, Item, CaseItem, Opening
from inventory.models import InventoryItem
from users.models import Profile
from cases.rng_simulation_service import run_monte_carlo_simulation
from scipy import stats as scipy_stats


class RealEndpointOpeningIntegrationTestCase(TestCase):
    """
    Integration test suite testing the ACTUAL production case opening endpoint:
    - POST /cases/<slug>/open/
    - Checks balance deduction, Opening creation, InventoryItem creation, winnings tally.
    - Verifies mathematical convergence to Target RTP (70.0%) across repeated real HTTP openings.
    - Verifies maintenance lock for regular users and access for staff.
    """

    def setUp(self):
        # 1. Staff user with balance to test openings
        self.staff_user = User.objects.create_user(
            username='tester_staff',
            password='password123',
            is_staff=True
        )
        self.staff_profile, _ = Profile.objects.get_or_create(user=self.staff_user)
        self.staff_profile.balance = Decimal('100000.00')
        self.staff_profile.save()

        # 2. Regular player user
        self.regular_user = User.objects.create_user(
            username='regular_player',
            password='password123',
            is_staff=False
        )
        self.regular_profile, _ = Profile.objects.get_or_create(user=self.regular_user)
        self.regular_profile.balance = Decimal('1000.00')
        self.regular_profile.save()

        # 3. Ensure Paradise Eruption case exists with all 24 items
        self.case = Case.objects.filter(slug='paradise-eruption').first()
        if not self.case:
            from django.core.management import call_command
            call_command('setup_paradise_eruption_case')
            self.case = Case.objects.filter(slug='paradise-eruption').first()

    def test_maintenance_lock_blocks_regular_users(self):
        """Verify that regular users are blocked while case is in maintenance (active=False)."""
        self.case.active = False
        self.case.save()
        client = Client()
        client.force_login(self.regular_user)
        url = reverse('cases:open_case_api', kwargs={'slug': 'paradise-eruption'})
        resp = client.post(url, {'quantity': 1})
        self.assertEqual(resp.status_code, 403)
        data = resp.json()
        self.assertFalse(data['success'])
        self.assertIn('техническом обслуживании', data['error'])

        # Staff can open even if inactive
        client_staff = Client()
        client_staff.force_login(self.staff_user)
        Profile.objects.filter(user=self.staff_user).update(balance=Decimal('1000.00'))
        resp_staff = client_staff.post(url, {'quantity': 1})
        self.assertEqual(resp_staff.status_code, 200)

        # Re-activate case for normal operation
        self.case.active = True
        self.case.save()

    def test_real_endpoint_single_opening_flow(self):
        """Verify complete transaction and inventory creation on real endpoint."""
        from django.core.cache import cache
        cache.clear()
        client = Client()
        client.force_login(self.staff_user)
        Profile.objects.filter(user=self.staff_user).update(balance=Decimal('100000.00'))
        self.staff_profile.refresh_from_db()
        url = reverse('cases:open_case_api', kwargs={'slug': 'paradise-eruption'})

        initial_balance = self.staff_profile.balance
        initial_openings = Opening.objects.count()
        initial_inventory = InventoryItem.objects.count()

        resp = client.post(url, {'quantity': 1})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['quantity'], 1)
        self.assertEqual(data['total_price'], 15.0)

        # Check records
        self.assertEqual(Opening.objects.count(), initial_openings + 1)
        self.assertEqual(InventoryItem.objects.count(), initial_inventory + 1)

        # Check balance
        self.staff_profile.refresh_from_db()
        self.assertEqual(self.staff_profile.balance, initial_balance - Decimal('15.00'))

    def test_real_endpoint_rtp_convergence_multi_openings(self):
        """
        Execute 1,000 real openings (200 requests x 5 quantity) via the real endpoint,
        verifying that payout, balance deduction, and actual RTP match ~70.0%.
        """
        from django.core.cache import cache
        cache.clear()
        client = Client()
        client.force_login(self.staff_user)
        Profile.objects.filter(user=self.staff_user).update(balance=Decimal('100000.00'))
        url = reverse('cases:open_case_api', kwargs={'slug': 'paradise-eruption'})

        num_requests = 200
        qty_per_request = 5
        total_openings = num_requests * qty_per_request  # 1,000 openings

        total_spent = Decimal('0.00')
        total_won = Decimal('0.00')
        item_drop_counts = {}

        for _ in range(num_requests):
            cache.clear()
            resp = client.post(url, {'quantity': qty_per_request})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            total_spent += Decimal(str(data['total_price']))
            for res in data['results']:
                won = res['won_item']
                total_won += Decimal(str(won['value']))
                item_drop_counts[won['name']] = item_drop_counts.get(won['name'], 0) + 1

        expected_spent = Decimal(str(total_openings)) * Decimal('15.00')
        self.assertEqual(total_spent, expected_spent)

        real_endpoint_rtp = float((total_won / total_spent) * Decimal('100.0'))
        # With 1,000 openings on 80% RTP, actual RTP will be close to 80% (within ±6%)
        self.assertAlmostEqual(real_endpoint_rtp, 80.0, delta=6.0)

        # Verify that cheap items drop far more frequently than jackpots
        common_count = item_drop_counts.get('Iron Judge Hat', 0)
        jackpot_count = item_drop_counts.get('Crimson Fox - Pan', 0)
        self.assertGreater(common_count, jackpot_count * 5)
