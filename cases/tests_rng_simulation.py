from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse

from cases.models import Case, Item, CaseItem, Opening, RngSimulationRun
from inventory.models import InventoryItem
from payments.models import Transaction
from users.models import Profile, AdminPermissionProfile
from cases.rng_simulation_service import run_monte_carlo_simulation


class RngSimulationTestCase(TestCase):
    """
    Automated test suite for Provably Fair Server-Side RNG Simulation tool:
    - Permission checks (superuser, staff with perm, staff without perm, regular user, anonymous).
    - Strict non-destructiveness (zero Opening, Transaction, InventoryItem, balance records).
    - Statistical convergence to Target RTP (100,000 rolls on 70% RTP Paradise Eruption).
    """

    def setUp(self):
        # 1. Test Users
        self.superuser = User.objects.create_superuser(username='boss_admin', password='password123', email='boss@example.com')
        
        self.staff_with_perm = User.objects.create_user(username='math_staff', password='password123', is_staff=True)
        AdminPermissionProfile.objects.create(user=self.staff_with_perm, can_run_rng_simulation=True)

        self.staff_without_perm = User.objects.create_user(username='regular_staff', password='password123', is_staff=True)
        AdminPermissionProfile.objects.create(user=self.staff_without_perm, can_run_rng_simulation=False)

        self.regular_user = User.objects.create_user(username='player1', password='password123', is_staff=False)
        self.profile, _ = Profile.objects.get_or_create(user=self.regular_user)
        self.profile.balance = Decimal('500.00')
        self.profile.save()

        # 2. Test Case & Items (Target RTP = 70.0% on 15.00 UC)
        self.case = Case.objects.create(
            name="Paradise Eruption Test",
            slug="paradise-eruption-test",
            price=Decimal('15.00'),
            active=True
        )

        # 3 items with distinct values and weights totaling EV = 10.50 UC (70% RTP)
        # Item 1: 5.00 UC, weight 50% (EV component = 2.50 UC)
        # Item 2: 10.00 UC, weight 30% (EV component = 3.00 UC)
        # Item 3: 25.00 UC, weight 20% (EV component = 5.00 UC)
        # Total EV = 10.50 UC, RTP = 10.50 / 15.00 = 70.0%
        item1 = Item.objects.create(weapon_type="AK-47", skin_name="Common", value=Decimal('5.00'), rarity="consumer")
        item2 = Item.objects.create(weapon_type="M4A4", skin_name="Rare", value=Decimal('10.00'), rarity="restricted")
        item3 = Item.objects.create(weapon_type="AWP", skin_name="Mythic", value=Decimal('25.00'), rarity="covert")

        CaseItem.objects.create(case=self.case, item=item1, weight=50.0)
        CaseItem.objects.create(case=self.case, item=item2, weight=30.0)
        CaseItem.objects.create(case=self.case, item=item3, weight=20.0)

    def test_permissions_gui_access(self):
        """Verify access rules for the main RNG simulation view."""
        url = reverse('admin_rng_simulation')

        # 1. Anonymous -> Redirect to login
        client = Client()
        resp = client.get(url)
        self.assertIn(resp.status_code, [302, 403])

        # 2. Regular user -> Redirect to admin login or forbidden
        client.force_login(self.regular_user)
        resp = client.get(url)
        self.assertIn(resp.status_code, [302, 403])

        # 3. Staff without can_run_rng_simulation -> 403 Forbidden
        client.force_login(self.staff_without_perm)
        resp = client.get(url)
        self.assertEqual(resp.status_code, 403)

        # 4. Staff WITH can_run_rng_simulation -> 200 OK
        client.force_login(self.staff_with_perm)
        resp = client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Симуляция честного серверного RNG")

        # 5. Superuser -> 200 OK
        client.force_login(self.superuser)
        resp = client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_permissions_ajax_endpoint(self):
        """Verify access rules for the AJAX simulation run endpoint."""
        url = reverse('admin_ajax_run_rng_simulation')
        payload = {'case_id': self.case.id, 'num_simulations': 1000}

        # Staff without perm -> 403
        client = Client()
        client.force_login(self.staff_without_perm)
        resp = client.post(url, payload, content_type='application/json')
        self.assertEqual(resp.status_code, 403)

        # Staff with perm -> 200 Success
        client.force_login(self.staff_with_perm)
        resp = client.post(url, payload, content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['data']['num_simulations'], 1000)

    def test_strict_non_destructiveness(self):
        """
        Ensure that running Monte Carlo simulations creates ZERO Opening, Transaction,
        or Inventory records, and does NOT alter any player balances.
        """
        initial_openings = Opening.objects.count()
        initial_transactions = Transaction.objects.count()
        initial_inventory = InventoryItem.objects.count()
        initial_balance = self.profile.balance

        # Run 10,000 simulations
        result = run_monte_carlo_simulation(
            case=self.case,
            num_simulations=10000,
            user=self.staff_with_perm,
            save_run=True
        )

        # Verify zero real gaming records were created
        self.assertEqual(Opening.objects.count(), initial_openings)
        self.assertEqual(Transaction.objects.count(), initial_transactions)
        self.assertEqual(InventoryItem.objects.count(), initial_inventory)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, initial_balance)

        # Verify simulation was recorded in RngSimulationRun only
        self.assertEqual(RngSimulationRun.objects.count(), 1)
        run_record = RngSimulationRun.objects.first()
        self.assertEqual(run_record.num_simulations, 10000)
        self.assertEqual(run_record.case, self.case)

    def test_statistical_convergence(self):
        """
        Verify that on 50,000 iterations, the simulated RTP converges to 70.0%
        within tight statistical bounds and Chi-Square p-value is valid.
        """
        result = run_monte_carlo_simulation(
            case=self.case,
            num_simulations=50000,
            save_run=False
        )

        self.assertEqual(result['target_rtp'], 70.0)
        self.assertAlmostEqual(result['actual_rtp'], 70.0, delta=2.0)
        self.assertEqual(result['total_spent'], 50000 * 15.0)

        # Check that Chi-square test was calculated
        self.assertIn('chi_square_stat', result)
        self.assertIn('p_value', result)
        self.assertGreaterEqual(result['p_value'], 0.0)
        self.assertLessEqual(result['p_value'], 1.0)
        self.assertIn(result['status_level'], ['green', 'yellow', 'red'])

        # Check item breakdown
        items = result['items']
        self.assertEqual(len(items), 3)
        total_actual_drops = sum(it['drop_count'] for it in items)
        self.assertEqual(total_actual_drops, 50000)

        # Check 95% confidence interval
        self.assertLessEqual(result['ci_lower'], result['actual_rtp'])
        self.assertGreaterEqual(result['ci_upper'], result['actual_rtp'])
