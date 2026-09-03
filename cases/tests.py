from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
import json

from cases.models import (
    Case, Item, CaseItem, Opening,
    PersonalCaseChance, PromoCode, PromoCodeUse, UserFreeOpening
)
from inventory.models import InventoryItem
from payments.models import Transaction
from payments.services import modify_user_balance
from payments.admin import approve_deposits
from cases.provably_fair import (
    calculate_provably_fair_roll, hash_seed, generate_server_seed,
    get_effective_case_chances
)

class NeonDropComprehensiveTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.user = User.objects.create_user(username='SecurityUser', password='StrongPassword123!', email='sec@neondrop.gg')
        self.profile = self.user.profile
        self.profile.balance = Decimal('100.00')
        self.profile.save()

        # Other user for permission tests
        self.other_user = User.objects.create_user(username='VictimUser', password='StrongPassword123!', email='victim@neondrop.gg')
        self.other_profile = self.other_user.profile
        self.other_profile.balance = Decimal('50.00')
        self.other_profile.save()

        # Staff admin user
        self.admin_user = User.objects.create_superuser(username='AdminUser', password='AdminPassword123!', email='admin@neondrop.gg')

        # Create Items
        self.knife = Item.objects.create(
            weapon_type='Karambit', skin_name='Fade', value=Decimal('1450.00'), rarity='knife', image_url='knife_karambit_fade'
        )
        self.rifle = Item.objects.create(
            weapon_type='AK-47', skin_name='Neon Rider', value=Decimal('42.31'), rarity='covert', image_url='ak47_neon_rider'
        )
        self.pistol = Item.objects.create(
            weapon_type='USP-S', skin_name='Cortex', value=Decimal('18.73'), rarity='classified', image_url='usps_cortex'
        )
        self.cheap_gun = Item.objects.create(
            weapon_type='P90', skin_name='Asiimov', value=Decimal('15.23'), rarity='mil_spec', image_url='p90_asiimov'
        )

        # Create Case ($10.00)
        self.case = Case.objects.create(
            name='Cyber Security Case', slug='cyber-sec-case', price=Decimal('10.00'), color_theme='cyber-pink', active=True
        )
        CaseItem.objects.create(case=self.case, item=self.knife, weight=0.02)
        CaseItem.objects.create(case=self.case, item=self.rifle, weight=0.5)
        CaseItem.objects.create(case=self.case, item=self.pistol, weight=5.0)
        CaseItem.objects.create(case=self.case, item=self.cheap_gun, weight=94.48)

    # ==================== BASIC SECURITY TESTS ====================
    def test_unauthorized_case_opening_rejected(self):
        """Unauthenticated user cannot open cases."""
        response = self.client.post(reverse('cases:open_case_api', kwargs={'slug': self.case.slug}))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Opening.objects.count(), 0)

    def test_insufficient_balance_rejected(self):
        """User with insufficient balance is rejected, balance remains untouched, no opening created."""
        self.profile.balance = Decimal('5.00')
        self.profile.save()

        self.client.login(username='SecurityUser', password='StrongPassword123!')
        response = self.client.post(reverse('cases:open_case_api', kwargs={'slug': self.case.slug}))
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('Недостаточно средств', data['error'])

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('5.00'))
        self.assertEqual(Opening.objects.count(), 0)
        self.assertEqual(InventoryItem.objects.count(), 0)

    def test_client_tampering_ignored(self):
        """Client sending fake price or fake item is ignored; authoritative DB price and server roll are used."""
        self.client.login(username='SecurityUser', password='StrongPassword123!')
        
        response = self.client.post(
            reverse('cases:open_case_api', kwargs={'slug': self.case.slug}),
            {
                'price': '0.01',
                'balance': '999999.00',
                'won_item': 'Karambit',
                'client_seed': 'attacker_seed_777'
            }
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('90.00'))

        tx = Transaction.objects.filter(user=self.user, transaction_type='case_open').latest('created_at')
        self.assertEqual(tx.amount, Decimal('-10.00'))
        self.assertEqual(tx.balance_before, Decimal('100.00'))
        self.assertEqual(tx.balance_after, Decimal('90.00'))

    def test_idempotency_duplicate_prevention(self):
        """Duplicate request with same idempotency key is rejected."""
        self.client.login(username='SecurityUser', password='StrongPassword123!')
        idempotency_key = 'unique_request_uuid_999'

        res1 = self.client.post(
            reverse('cases:open_case_api', kwargs={'slug': self.case.slug}),
            {'idempotency_key': idempotency_key}
        )
        self.assertEqual(res1.status_code, 200)

        res2 = self.client.post(
            reverse('cases:open_case_api', kwargs={'slug': self.case.slug}),
            {'idempotency_key': idempotency_key}
        )
        self.assertEqual(res2.status_code, 409)

    def test_cannot_sell_other_users_item(self):
        """User cannot sell items belonging to another user."""
        victim_item = InventoryItem.objects.create(user=self.other_user, item=self.knife, source='case')
        
        self.client.login(username='SecurityUser', password='StrongPassword123!')
        response = self.client.post(reverse('inventory:sell_item', kwargs={'item_id': victim_item.id}))
        
        self.assertEqual(response.status_code, 400)
        victim_item.refresh_from_db()
        self.assertFalse(victim_item.is_sold)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('100.00'))

    def test_cannot_sell_already_sold_item(self):
        """Second sell attempt on an already sold item is rejected."""
        user_item = InventoryItem.objects.create(user=self.user, item=self.pistol, source='case')
        self.client.login(username='SecurityUser', password='StrongPassword123!')

        res1 = self.client.post(reverse('inventory:sell_item', kwargs={'item_id': user_item.id}))
        self.assertEqual(res1.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('118.73'))

        res2 = self.client.post(reverse('inventory:sell_item', kwargs={'item_id': user_item.id}))
        self.assertEqual(res2.status_code, 400)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('118.73'))

    def test_deposit_flow_requires_admin_approval(self):
        """Deposit creation does not alter balance automatically; admin approval credits balance atomically."""
        self.client.login(username='SecurityUser', password='StrongPassword123!')
        
        res = self.client.post(reverse('payments:create_request'), {'amount': '50'})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        
        tx_id = data['transaction_id']
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('100.00'))
        
        tx = Transaction.objects.get(id=tx_id)
        self.assertEqual(tx.status, 'pending')

        approve_deposits(None, type('Req', (), {'user': self.admin_user})(), Transaction.objects.filter(id=tx_id))
        
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('150.00'))
        tx.refresh_from_db()
        self.assertEqual(tx.status, 'completed')

    def test_provably_fair_verification(self):
        """Provably fair HMAC-SHA256 roll calculation is deterministic and bounded [0.0, 1.0)."""
        server_seed = generate_server_seed()
        client_seed = "client_entropy_456"
        nonce = 1

        roll1 = calculate_provably_fair_roll(server_seed, client_seed, nonce)
        roll2 = calculate_provably_fair_roll(server_seed, client_seed, nonce)

        self.assertEqual(roll1, roll2)
        self.assertGreaterEqual(roll1, 0.0)
        self.assertLess(roll1, 1.0)
        self.assertEqual(hash_seed(server_seed), hash_seed(server_seed))

    # ==================== MULTI-CASE OPENING (1 to 5) TESTS ====================
    def test_multi_case_opening_1_to_5_and_rejections(self):
        """Test opening 1, 2, 3, 4, 5 cases and rejecting invalid quantities (0, 6, -1, non-int)."""
        self.client.login(username='SecurityUser', password='StrongPassword123!')

        # 1. Invalid quantities are rejected with HTTP 400
        for bad_qty in [0, 6, -1, 100, 'abc']:
            res = self.client.post(
                reverse('cases:open_case_api', kwargs={'slug': self.case.slug}),
                {'quantity': bad_qty}
            )
            self.assertEqual(res.status_code, 400)
            data = res.json()
            self.assertFalse(data['success'])

        # 2. Open 1 Case ($10.00)
        res1 = self.client.post(
            reverse('cases:open_case_api', kwargs={'slug': self.case.slug}),
            {'quantity': 1}
        )
        self.assertEqual(res1.status_code, 200)
        d1 = res1.json()
        self.assertTrue(d1['success'])
        self.assertEqual(d1['quantity'], 1)
        self.assertEqual(len(d1['results']), 1)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('90.00'))

        # 3. Open 2 Cases ($20.00)
        res2 = self.client.post(
            reverse('cases:open_case_api', kwargs={'slug': self.case.slug}),
            {'quantity': 2}
        )
        self.assertEqual(res2.status_code, 200)
        d2 = res2.json()
        self.assertEqual(d2['quantity'], 2)
        self.assertEqual(len(d2['results']), 2)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('70.00'))

        # 4. Open 3 Cases ($30.00)
        res3 = self.client.post(
            reverse('cases:open_case_api', kwargs={'slug': self.case.slug}),
            {'quantity': 3}
        )
        self.assertEqual(res3.status_code, 200)
        d3 = res3.json()
        self.assertEqual(d3['quantity'], 3)
        self.assertEqual(len(d3['results']), 3)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('40.00'))

        # 5. Open 4 Cases ($40.00)
        res4 = self.client.post(
            reverse('cases:open_case_api', kwargs={'slug': self.case.slug}),
            {'quantity': 4}
        )
        self.assertEqual(res4.status_code, 200)
        d4 = res4.json()
        self.assertEqual(d4['quantity'], 4)
        self.assertEqual(len(d4['results']), 4)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('0.00'))

        # 6. Open 5 Cases when balance is $0.00 -> Rejected
        res5_fail = self.client.post(
            reverse('cases:open_case_api', kwargs={'slug': self.case.slug}),
            {'quantity': 5}
        )
        self.assertEqual(res5_fail.status_code, 400)

        # 7. Grant balance and open 5 Cases ($50.00)
        self.profile.balance = Decimal('50.00')
        self.profile.save()
        res5 = self.client.post(
            reverse('cases:open_case_api', kwargs={'slug': self.case.slug}),
            {'quantity': 5}
        )
        self.assertEqual(res5.status_code, 200)
        d5 = res5.json()
        self.assertEqual(d5['quantity'], 5)
        self.assertEqual(len(d5['results']), 5)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('0.00'))

    def test_free_case_openings_deduction_priority(self):
        """Free openings are deducted before balance debit."""
        self.client.login(username='SecurityUser', password='StrongPassword123!')
        self.profile.balance = Decimal('10.00')
        self.profile.save()

        # Grant 2 free openings for this case
        UserFreeOpening.objects.create(user=self.user, case=self.case, openings_left=2, total_granted=2)

        # Open 3 cases: 2 free + 1 paid ($10.00)
        res = self.client.post(
            reverse('cases:open_case_api', kwargs={'slug': self.case.slug}),
            {'quantity': 3}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['free_openings_used'], 2)
        self.assertEqual(data['paid_quantity'], 1)
        self.assertEqual(data['total_price'], 10.00)
        self.assertEqual(data['free_openings_remaining'], 0)

        # Profile balance debited only for 1 paid case ($100 - $10 = $0 from $10)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('0.00'))

        # Free opening record updated
        ufo = UserFreeOpening.objects.get(user=self.user, case=self.case)
        self.assertEqual(ufo.openings_left, 0)

    # ==================== PROMO CODE SYSTEM TESTS ====================
    def test_promocode_coins_bonus_success_and_ledger(self):
        """Activating a valid coins promo code credits balance and creates Transaction record."""
        self.client.login(username='SecurityUser', password='StrongPassword123!')
        now = timezone.now()

        promo = PromoCode.objects.create(
            code='NEON100',
            bonus_type='coins',
            bonus_value=Decimal('100.00'),
            max_uses=10,
            starts_at=now - timedelta(days=1),
            expires_at=now + timedelta(days=30),
            is_active=True
        )

        res = self.client.post(reverse('cases:api_redeem_promocode'), {'code': 'neon100'})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['new_balance'], 200.00)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('200.00'))

        # Verify PromoCode counter incremented
        promo.refresh_from_db()
        self.assertEqual(promo.used_count, 1)

        # Verify PromoCodeUse record created
        use = PromoCodeUse.objects.get(user=self.user, promo_code=promo)
        self.assertEqual(use.bonus_amount, Decimal('100.00'))
        self.assertIsNotNone(use.related_transaction)
        self.assertEqual(use.related_transaction.transaction_type, 'promo_bonus')

    def test_promocode_free_openings_bonus(self):
        """Activating a free openings promo code grants free openings for the specific case."""
        self.client.login(username='SecurityUser', password='StrongPassword123!')
        now = timezone.now()

        promo = PromoCode.objects.create(
            code='FREE5',
            bonus_type='free_case_opens',
            bonus_value=Decimal('5.00'),
            case=self.case,
            max_uses=50,
            starts_at=now - timedelta(days=1),
            expires_at=now + timedelta(days=30),
            is_active=True
        )

        res = self.client.post(reverse('cases:api_redeem_promocode'), {'code': 'FREE5'})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])

        ufo = UserFreeOpening.objects.get(user=self.user, case=self.case)
        self.assertEqual(ufo.openings_left, 5)

    def test_promocode_duplicate_use_rejected(self):
        """User cannot redeem the same promo code twice."""
        self.client.login(username='SecurityUser', password='StrongPassword123!')
        now = timezone.now()

        promo = PromoCode.objects.create(
            code='ONCEONLY',
            bonus_type='coins',
            bonus_value=Decimal('25.00'),
            max_uses=100,
            starts_at=now - timedelta(days=1),
            expires_at=now + timedelta(days=10),
            is_active=True
        )

        # First activation succeeds
        res1 = self.client.post(reverse('cases:api_redeem_promocode'), {'code': 'ONCEONLY'})
        self.assertEqual(res1.status_code, 200)

        # Second activation fails
        res2 = self.client.post(reverse('cases:api_redeem_promocode'), {'code': 'ONCEONLY'})
        self.assertEqual(res2.status_code, 400)
        data = res2.json()
        self.assertFalse(data['success'])
        self.assertIn('уже активировали', data['error'])

    def test_promocode_expired_or_inactive_or_limit_reached(self):
        """Expired, inactive, or max-uses exceeded promo codes are rejected."""
        self.client.login(username='SecurityUser', password='StrongPassword123!')
        now = timezone.now()

        # 1. Expired Code
        expired = PromoCode.objects.create(
            code='EXPIRED1', bonus_type='coins', bonus_value=Decimal('10.00'),
            starts_at=now - timedelta(days=10), expires_at=now - timedelta(days=1), is_active=True
        )
        res_exp = self.client.post(reverse('cases:api_redeem_promocode'), {'code': 'EXPIRED1'})
        self.assertEqual(res_exp.status_code, 400)
        self.assertIn('истёк', res_exp.json()['error'])

        # 2. Inactive Code
        inactive = PromoCode.objects.create(
            code='INACTIVE1', bonus_type='coins', bonus_value=Decimal('10.00'),
            starts_at=now - timedelta(days=1), expires_at=now + timedelta(days=10), is_active=False
        )
        res_inact = self.client.post(reverse('cases:api_redeem_promocode'), {'code': 'INACTIVE1'})
        self.assertEqual(res_inact.status_code, 400)
        self.assertIn('выключен', res_inact.json()['error'])

        # 3. Limit reached Code
        full = PromoCode.objects.create(
            code='LIMITFULL', bonus_type='coins', bonus_value=Decimal('10.00'),
            max_uses=2, used_count=2,
            starts_at=now - timedelta(days=1), expires_at=now + timedelta(days=10), is_active=True
        )
        res_full = self.client.post(reverse('cases:api_redeem_promocode'), {'code': 'LIMITFULL'})
        self.assertEqual(res_full.status_code, 400)
        self.assertIn('исчерпан', res_full.json()['error'])

    # ==================== PERSONAL CASE CHANCES & PROBABILITY NORMALIZATION ====================
    def test_personal_chance_normalization_and_application(self):
        """Active PersonalCaseChance sets exact boosted probability and mathematically normalizes all items to 100%."""
        now = timezone.now()

        # 1. Base probabilities for unpromoted user strictly sum to 100%
        base_chances = get_effective_case_chances(self.case, self.other_user)
        base_prob_sum = sum(item['probability'] for item in base_chances)
        self.assertAlmostEqual(base_prob_sum, 1.0, places=5)
        
        # Knife base chance is ~0.02%
        knife_base = next(item for item in base_chances if item['item'].id == self.knife.id)
        self.assertAlmostEqual(knife_base['probability'], 0.0002, places=4)

        # 2. Assign 10.00% Personal Chance for SecurityUser on Knife
        promo = PersonalCaseChance.objects.create(
            user=self.user,
            case=self.case,
            item=self.knife,
            chance=Decimal('10.00'),
            starts_at=now - timedelta(days=1),
            expires_at=now + timedelta(days=7),
            is_active=True
        )

        # Promoted user chances
        promoted_chances = get_effective_case_chances(self.case, self.user)
        promoted_prob_sum = sum(item['probability'] for item in promoted_chances)
        self.assertAlmostEqual(promoted_prob_sum, 1.0, places=5)

        knife_promoted = next(item for item in promoted_chances if item['item'].id == self.knife.id)
        self.assertEqual(knife_promoted['probability'], 0.10)
        self.assertTrue(knife_promoted['is_promoted'])

        # Other user remains on base chances
        other_chances = get_effective_case_chances(self.case, self.other_user)
        knife_other = next(item for item in other_chances if item['item'].id == self.knife.id)
        self.assertAlmostEqual(knife_other['probability'], 0.0002, places=4)

        # 3. If Personal Chance is expired, falls back to normal base chances
        promo.expires_at = now - timedelta(hours=1)
        promo.save()

        expired_chances = get_effective_case_chances(self.case, self.user)
        knife_expired = next(item for item in expired_chances if item['item'].id == self.knife.id)
        self.assertAlmostEqual(knife_expired['probability'], 0.0002, places=4)
        self.assertFalse(knife_expired['is_promoted'])

    def test_inventory_and_upgrades_views_render(self):
        """Verify /inventory/, /upgrade/, and /contracts/ render with HTTP 200 without FieldError."""
        InventoryItem.objects.create(user=self.user, item=self.pistol, source='case')
        self.client.login(username='SecurityUser', password='StrongPassword123!')

        res_inv = self.client.get(reverse('inventory:index'))
        self.assertEqual(res_inv.status_code, 200)

        res_upg = self.client.get(reverse('upgrades:index'))
        self.assertEqual(res_upg.status_code, 200)

        res_ctr = self.client.get(reverse('contracts:index'))
        self.assertEqual(res_ctr.status_code, 200)
