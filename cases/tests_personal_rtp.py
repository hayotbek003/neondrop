from decimal import Decimal
from datetime import timedelta
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone

from cases.models import Category, Item, Case, CaseItem, Opening, PersonalRtpBonus
from cases.provably_fair import get_effective_case_chances, select_weighted_item
from inventory.models import InventoryItem
from users.models import Profile


class PersonalRtpBonusComprehensiveTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.now = timezone.now()

        # Users
        self.bonus_user = User.objects.create_user(username='lucky_winner', password='Password123!', email='lucky@neondrop.io')
        self.regular_user = User.objects.create_user(username='regular_player', password='Password123!', email='regular@neondrop.io')
        self.admin_user = User.objects.create_superuser(username='admin_boss', password='Password123!', email='admin@neondrop.io')

        # Balance setup
        self.bonus_profile = Profile.objects.get(user=self.bonus_user)
        self.bonus_profile.balance = Decimal('100000.00')
        self.bonus_profile.save()

        self.regular_profile = Profile.objects.get(user=self.regular_user)
        self.regular_profile.balance = Decimal('100000.00')
        self.regular_profile.save()

        # Category
        self.cat = Category.objects.create(name='Supercars', slug='supercars')

        # Create Case 1: Porsche 911 GT3 RS (Price: 20000 UC)
        self.case_porsche = Case.objects.create(
            name='Porsche 911 GT3 RS',
            slug='porsche-911-gt3-rs-test',
            category=self.cat,
            price=Decimal('20000.00'),
            active=True
        )
        self.porsche_items = [
            Item.objects.create(name='Porsche Common', weapon_type='Vehicle', skin_name='Common', value=Decimal('4000.00'), rarity='mil-spec'),
            Item.objects.create(name='Porsche Mid', weapon_type='Vehicle', skin_name='Mid', value=Decimal('15000.00'), rarity='classified'),
            Item.objects.create(name='Porsche Rare', weapon_type='Vehicle', skin_name='Rare', value=Decimal('30000.00'), rarity='covert'),
            Item.objects.create(name='Porsche Jackpot', weapon_type='Vehicle', skin_name='Jackpot', value=Decimal('45000.00'), rarity='knife'),
        ]
        weights_porsche = [5000, 3000, 1500, 500]
        self.ci_porsche = []
        for it, w in zip(self.porsche_items, weights_porsche):
            self.ci_porsche.append(CaseItem.objects.create(case=self.case_porsche, item=it, weight=w))

        # Create Case 2: Ferrari (Price: 10000 UC)
        self.case_ferrari = Case.objects.create(
            name='Ferrari Test',
            slug='ferrari-test',
            category=self.cat,
            price=Decimal('10000.00'),
            active=True
        )
        self.ferrari_items = [
            Item.objects.create(name='Ferrari Low', weapon_type='Vehicle', skin_name='Low', value=Decimal('4000.00'), rarity='mil-spec'),
            Item.objects.create(name='Ferrari Mid', weapon_type='Vehicle', skin_name='Mid', value=Decimal('9000.00'), rarity='restricted'),
            Item.objects.create(name='Ferrari High', weapon_type='Vehicle', skin_name='High', value=Decimal('40000.00'), rarity='knife'),
        ]
        weights_ferrari = [6000, 3000, 1000]
        self.ci_ferrari = []
        for it, w in zip(self.ferrari_items, weights_ferrari):
            self.ci_ferrari.append(CaseItem.objects.create(case=self.case_ferrari, item=it, weight=w))

    def _calc_rtp(self, chances, case_price):
        ev = sum(entry['probability'] * float(entry['item'].value) for entry in chances)
        return (ev / float(case_price)) * 100.0

    def test_user_with_bonus_receives_95_percent_rtp(self):
        bonus = PersonalRtpBonus.objects.create(
            user=self.bonus_user,
            target_rtp=Decimal('95.00'),
            start_date=self.now - timedelta(days=1),
            end_date=self.now + timedelta(days=7),
            is_active=True
        )
        self.assertTrue(bonus.is_valid_now)

        chances_porsche = get_effective_case_chances(self.case_porsche, self.bonus_user)
        prob_sum_porsche = sum(c['probability'] for c in chances_porsche)
        self.assertAlmostEqual(prob_sum_porsche, 1.0, places=5)
        rtp_porsche = self._calc_rtp(chances_porsche, self.case_porsche.price)
        self.assertAlmostEqual(rtp_porsche, 95.0, delta=0.01)

        chances_ferrari = get_effective_case_chances(self.case_ferrari, self.bonus_user)
        prob_sum_ferrari = sum(c['probability'] for c in chances_ferrari)
        self.assertAlmostEqual(prob_sum_ferrari, 1.0, places=5)
        rtp_ferrari = self._calc_rtp(chances_ferrari, self.case_ferrari.price)
        self.assertAlmostEqual(rtp_ferrari, 95.0, delta=0.01)

    def test_user_without_bonus_receives_standard_rtp(self):
        chances_regular = get_effective_case_chances(self.case_porsche, self.regular_user)
        prob_sum = sum(c['probability'] for c in chances_regular)
        self.assertAlmostEqual(prob_sum, 1.0, places=5)

        total_w = sum(ci.weight for ci in self.ci_porsche)
        expected_base_ev = sum((ci.weight / total_w) * float(ci.item.value) for ci in self.ci_porsche)
        expected_base_rtp = (expected_base_ev / float(self.case_porsche.price)) * 100.0

        actual_rtp = self._calc_rtp(chances_regular, self.case_porsche.price)
        self.assertAlmostEqual(actual_rtp, expected_base_rtp, places=4)

        chances_anon = get_effective_case_chances(self.case_porsche, None)
        self.assertAlmostEqual(self._calc_rtp(chances_anon, self.case_porsche.price), expected_base_rtp, places=4)

    def test_expired_or_inactive_bonus_returns_standard_rtp(self):
        bonus = PersonalRtpBonus.objects.create(
            user=self.bonus_user,
            target_rtp=Decimal('95.00'),
            start_date=self.now - timedelta(days=10),
            end_date=self.now - timedelta(days=1),
            is_active=True
        )
        self.assertFalse(bonus.is_valid_now)

        total_w = sum(ci.weight for ci in self.ci_porsche)
        expected_base_rtp = (sum((ci.weight / total_w) * float(ci.item.value) for ci in self.ci_porsche) / float(self.case_porsche.price)) * 100.0

        expired_chances = get_effective_case_chances(self.case_porsche, self.bonus_user)
        self.assertAlmostEqual(self._calc_rtp(expired_chances, self.case_porsche.price), expected_base_rtp, places=4)

        bonus.start_date = self.now - timedelta(days=1)
        bonus.end_date = self.now + timedelta(days=5)
        bonus.is_active = False
        bonus.save()
        self.assertFalse(bonus.is_valid_now)

        deactivated_chances = get_effective_case_chances(self.case_porsche, self.bonus_user)
        self.assertAlmostEqual(self._calc_rtp(deactivated_chances, self.case_porsche.price), expected_base_rtp, places=4)

    def test_database_base_weights_remain_unmodified(self):
        weights_before = {ci.id: ci.weight for ci in CaseItem.objects.filter(case=self.case_porsche)}

        PersonalRtpBonus.objects.create(
            user=self.bonus_user,
            target_rtp=Decimal('95.00'),
            start_date=self.now - timedelta(days=1),
            end_date=self.now + timedelta(days=7),
            is_active=True
        )

        for i in range(20):
            chances = get_effective_case_chances(self.case_porsche, self.bonus_user)
            selected_ci, roll, s_hash = select_weighted_item(
                list(self.case_porsche.case_items.all()),
                f'server_seed_{i}', f'client_seed_{i}', i,
                user=self.bonus_user, case=self.case_porsche
            )
            self.assertIsNotNone(selected_ci)

        weights_after = {ci.id: ci.weight for ci in CaseItem.objects.filter(case=self.case_porsche)}
        self.assertEqual(weights_before, weights_after)

    def test_stealth_display_mode_does_not_leak_bonus(self):
        PersonalRtpBonus.objects.create(
            user=self.bonus_user,
            target_rtp=Decimal('95.00'),
            start_date=self.now - timedelta(days=1),
            end_date=self.now + timedelta(days=7),
            is_active=True
        )

        display_chances = get_effective_case_chances(self.case_porsche, self.bonus_user, for_display=True)
        for entry in display_chances:
            self.assertFalse(entry.get('is_promoted', False))

        total_w = sum(ci.weight for ci in self.ci_porsche)
        expected_base_rtp = (sum((ci.weight / total_w) * float(ci.item.value) for ci in self.ci_porsche) / float(self.case_porsche.price)) * 100.0
        display_rtp = self._calc_rtp(display_chances, self.case_porsche.price)
        self.assertAlmostEqual(display_rtp, expected_base_rtp, places=4)

    def test_open_case_api_executes_with_rtp_bonus_and_records_history(self):
        PersonalRtpBonus.objects.create(
            user=self.bonus_user,
            target_rtp=Decimal('95.00'),
            start_date=self.now - timedelta(days=1),
            end_date=self.now + timedelta(days=7),
            is_active=True
        )

        Profile.objects.filter(user=self.bonus_user).update(balance=Decimal('100000.00'))
        self.bonus_user.refresh_from_db()
        self.client.force_login(self.bonus_user)
        resp = self.client.post(f'/cases/{self.case_porsche.slug}/open/', {
            'quantity': 1,
            'client_seed': 'custom_test_seed_123'
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(len(data.get('results', [])), 1)

        result = data['results'][0]
        opening_id = result['opening_id']
        inv_id = result['inventory_id']

        opening = Opening.objects.get(id=opening_id)
        self.assertEqual(opening.user, self.bonus_user)
        self.assertEqual(opening.case, self.case_porsche)
        self.assertEqual(opening.price, self.case_porsche.price)
        self.assertIsNotNone(opening.item)

        inv = InventoryItem.objects.get(id=inv_id)
        self.assertEqual(inv.user, self.bonus_user)
        self.assertEqual(inv.item, opening.item)
        self.assertFalse(inv.is_sold)
