from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
import json
import os
from pathlib import Path

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

    def test_admin_models_render_without_operational_error(self):
        """Verify all Django Admin model changelist views render with HTTP 200 without OperationalError."""
        self.client.login(username='AdminUser', password='AdminPassword123!')

        # Create sample records to verify list displays
        now = timezone.now()
        promo = PromoCode.objects.create(
            code='ADMINTEST', bonus_type='coins', bonus_value=Decimal('50.00'),
            starts_at=now, expires_at=now + timedelta(days=5), is_active=True
        )
        PromoCodeUse.objects.create(promo_code=promo, user=self.user, bonus_amount=Decimal('50.00'))
        PersonalCaseChance.objects.create(
            user=self.user, case=self.case, item=self.knife, chance=Decimal('5.00'),
            starts_at=now, expires_at=now + timedelta(days=5), is_active=True
        )
        UserFreeOpening.objects.create(user=self.user, case=self.case, openings_left=3, total_granted=3)

        admin_urls = [
            '/admin/cases/promocode/',
            '/admin/cases/promocodeuse/',
            '/admin/cases/personalcasechance/',
            '/admin/cases/userfreeopening/',
            '/admin/cases/case/',
            '/admin/cases/item/',
            '/admin/cases/opening/',
            '/admin/contracts/contract/',
            '/admin/upgrades/upgradeattempt/',
            '/admin/battles/battle/',
            '/admin/inventory/inventoryitem/',
            '/admin/payments/transaction/',
            '/admin/users/profile/',
        ]

        for url in admin_urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, f"Failed rendering admin page {url}")

    def test_contracts_flow(self):
        """Verify contract craft burns input items, creates reward, and updates statistics."""
        self.client.login(username='SecurityUser', password='StrongPassword123!')
        i1 = InventoryItem.objects.create(user=self.user, item=self.cheap_gun, source='case')
        i2 = InventoryItem.objects.create(user=self.user, item=self.cheap_gun, source='case')
        i3 = InventoryItem.objects.create(user=self.user, item=self.pistol, source='case')

        # Craft contract via JSON
        res = self.client.post(
            reverse('contracts:create'),
            json.dumps({'item_ids': [i1.id, i2.id, i3.id]}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        self.assertIn('output_item', data)

        # Verify inputs burned
        i1.refresh_from_db()
        i2.refresh_from_db()
        i3.refresh_from_db()
        self.assertTrue(i1.is_sold)
        self.assertTrue(i2.is_sold)
        self.assertTrue(i3.is_sold)

        # Verify crafted item in inventory
        crafted = InventoryItem.objects.filter(user=self.user, source='contract').first()
        self.assertIsNotNone(crafted)

    def test_upgrades_flow(self):
        """Verify upgrade chance calculation and execution."""
        self.client.login(username='SecurityUser', password='StrongPassword123!')
        inv_item = InventoryItem.objects.create(user=self.user, item=self.pistol, source='case')

        # 1. Calc chance
        calc_res = self.client.get(
            reverse('upgrades:calculate_chance'),
            {'input_id': inv_item.id, 'target_id': self.rifle.id}
        )
        self.assertEqual(calc_res.status_code, 200)
        calc_data = calc_res.json()
        self.assertTrue(calc_data['success'])
        self.assertGreater(calc_data['chance_percent'], 0)

        # 2. Execute upgrade
        exec_res = self.client.post(
            reverse('upgrades:execute'),
            {'inventory_item_id': inv_item.id, 'target_item_id': self.rifle.id}
        )
        self.assertEqual(exec_res.status_code, 200)
        exec_data = exec_res.json()
        self.assertTrue(exec_data['success'])
        inv_item.refresh_from_db()
        self.assertTrue(inv_item.is_sold)

    def test_battles_flow(self):
        """Verify case battles creation vs bot, PvP creation, and joining."""
        from battles.models import Battle
        self.client.login(username='SecurityUser', password='StrongPassword123!')

        # 1. Create battle vs bot
        bot_res = self.client.post(
            reverse('battles:create'),
            {'case_id': self.case.id, 'rounds_count': 1, 'vs_bot': 'true'}
        )
        self.assertEqual(bot_res.status_code, 200)
        bot_data = bot_res.json()
        self.assertTrue(bot_data['success'])
        b_id = bot_data['battle_id']
        b = Battle.objects.get(id=b_id)
        self.assertEqual(b.status, 'finished')

        # 2. Create battle PvP
        pvp_res = self.client.post(
            reverse('battles:create'),
            {'case_id': self.case.id, 'rounds_count': 1, 'vs_bot': 'false'}
        )
        self.assertEqual(pvp_res.status_code, 200)
        pvp_data = pvp_res.json()
        pvp_b = Battle.objects.get(id=pvp_data['battle_id'])
        self.assertEqual(pvp_b.status, 'waiting')

        # 3. Join battle as other user
        self.client.login(username='VictimUser', password='StrongPassword123!')
        join_res = self.client.post(reverse('battles:join', kwargs={'battle_id': pvp_b.id}))
        self.assertEqual(join_res.status_code, 200)
        pvp_b.refresh_from_db()
        self.assertEqual(pvp_b.status, 'finished')
        self.assertIsNotNone(pvp_b.winner)

    def test_all_pages_render(self):
        """Verify all public and private pages render with HTTP 200."""
        self.client.login(username='SecurityUser', password='StrongPassword123!')

        routes = [
            reverse('cases:home'),
            reverse('cases:cases_list'),
            reverse('cases:case_detail', kwargs={'slug': self.case.slug}),
            reverse('cases:top'),
            reverse('cases:fairness'),
            reverse('users:profile'),
            reverse('users:history'),
            reverse('users:settings'),
            reverse('inventory:index'),
            reverse('upgrades:index'),
            reverse('contracts:index'),
            reverse('battles:index'),
            reverse('payments:deposit'),
        ]

        for route in routes:
            res = self.client.get(route)
            self.assertEqual(res.status_code, 200, f"Failed rendering route {route}")

    def test_persistent_authentication_and_session_lifecycle(self):
        """Verify persistent authentication across browser sessions, 30-day age, and complete logout cleanup."""
        from django.contrib.sessions.models import Session
        from django.conf import settings

        client = Client()

        # 1. Login with credentials
        login_res = client.post(reverse('users:login'), {
            'username_or_email': 'SecurityUser',
            'password': 'StrongPassword123!'
        })
        self.assertEqual(login_res.status_code, 302)

        # 2. Verify session cookie is set
        session_cookie_name = getattr(settings, 'SESSION_COOKIE_NAME', 'sessionid')
        self.assertIn(session_cookie_name, client.cookies)
        session_key = client.cookies[session_cookie_name].value

        # 3. Verify session exists in database (database-backed)
        db_session = Session.objects.filter(session_key=session_key).first()
        self.assertIsNotNone(db_session)

        # 4. Verify expiration is ~30 days in future (not browser close)
        now = timezone.now()
        expected_future = now + timedelta(days=29)
        self.assertGreater(db_session.expire_date, expected_future)

        # 5. Access authenticated page and API
        profile_res = client.get(reverse('users:profile'))
        self.assertEqual(profile_res.status_code, 200)
        self.assertContains(profile_res, 'SecurityUser')

        bal_res = client.get(reverse('users:api_balance'))
        self.assertEqual(bal_res.status_code, 200)
        self.assertEqual(bal_res.json()['username'], 'SecurityUser')

        # 6. Simulate browser restart (New Client instance reusing persistent session cookie)
        reopened_client = Client()
        reopened_client.cookies[session_cookie_name] = session_key

        reopened_res = reopened_client.get(reverse('users:profile'))
        self.assertEqual(reopened_res.status_code, 200)
        self.assertContains(reopened_res, 'SecurityUser')

        # 7. Logout
        logout_res = reopened_client.post(reverse('users:logout'))
        self.assertEqual(logout_res.status_code, 302)

        # 8. Verify session is wiped from DB and user cannot access protected routes
        db_session_after = Session.objects.filter(session_key=session_key).first()
        self.assertIsNone(db_session_after)

        protected_res = reopened_client.get(reverse('users:profile'))
        self.assertEqual(protected_res.status_code, 302)
        self.assertIn(reverse('users:login'), protected_res.url)

    def test_csrf_enforcement_and_validation(self):
        """Verify CSRF token generation, strict 403 rejection on missing/invalid token, and successful POST on valid token."""
        from django.middleware.csrf import get_token

        # 1. Test GET login page ensures CSRF cookie and meta tag
        client_get = Client()
        get_res = client_get.get(reverse('users:login'))
        self.assertEqual(get_res.status_code, 200)
        self.assertIn('csrftoken', client_get.cookies)
        self.assertContains(get_res, 'name="csrfmiddlewaretoken"')
        self.assertContains(get_res, 'name="csrf-token"')

        # 2. Test CSRF Enforcement: Missing CSRF token is rejected with 403
        strict_client = Client(enforce_csrf_checks=True)
        no_csrf_res = strict_client.post(reverse('users:login'), {
            'username_or_email': 'SecurityUser',
            'password': 'StrongPassword123!'
        })
        self.assertEqual(no_csrf_res.status_code, 403)

        # 3. Test CSRF Enforcement: Incorrect CSRF token is rejected with 403
        bad_token_res = strict_client.post(
            reverse('users:login'),
            {'username_or_email': 'SecurityUser', 'password': 'StrongPassword123!'},
            HTTP_X_CSRFTOKEN='invalid_corrupted_csrf_token_value_1234567890'
        )
        self.assertEqual(bad_token_res.status_code, 403)

        # 4. Test Valid CSRF Login POST
        login_page = strict_client.get(reverse('users:login'))
        csrf_token = login_page.cookies['csrftoken'].value

        valid_login_res = strict_client.post(
            reverse('users:login'),
            {
                'username_or_email': 'SecurityUser',
                'password': 'StrongPassword123!',
                'csrfmiddlewaretoken': csrf_token
            }
        )
        self.assertEqual(valid_login_res.status_code, 302)

        # 5. Test Valid CSRF Case Opening API with fresh post-login CSRF token in X-CSRFToken header
        fresh_csrf_token = strict_client.cookies['csrftoken'].value
        open_res = strict_client.post(
            reverse('cases:open_case_api', kwargs={'slug': self.case.slug}),
            {'quantity': 1},
            HTTP_X_CSRFTOKEN=fresh_csrf_token
        )
        self.assertEqual(open_res.status_code, 200)
        self.assertTrue(open_res.json()['success'])

        # 6. Test Valid CSRF Deposit Request API
        deposit_res = strict_client.post(
            reverse('payments:create_request'),
            {'amount': '50.00'},
            HTTP_X_CSRFTOKEN=fresh_csrf_token
        )
        self.assertEqual(deposit_res.status_code, 200)
        self.assertTrue(deposit_res.json()['success'])

        # 7. Test Valid CSRF PromoCode Redeem API
        PromoCode.objects.create(
            code='CSRFPROMO',
            bonus_type='coins',
            bonus_value=Decimal('50.00'),
            starts_at=timezone.now() - timedelta(days=1),
            expires_at=timezone.now() + timedelta(days=7),
            is_active=True
        )
        promo_res = strict_client.post(
            reverse('cases:redeem_promocode'),
            {'code': 'CSRFPROMO'},
            HTTP_X_CSRFTOKEN=fresh_csrf_token
        )
        self.assertEqual(promo_res.status_code, 200)
        self.assertTrue(promo_res.json()['success'])

        # 8. Test Valid CSRF Logout
        logout_res = strict_client.post(
            reverse('users:logout'),
            HTTP_X_CSRFTOKEN=fresh_csrf_token
        )
        self.assertEqual(logout_res.status_code, 302)

    def test_backup_and_restore_migration_integrity(self):
        """Verify full backup export, clean database restore, password hash preservation, and zero data loss."""
        from django.core.management import call_command
        import tempfile

        # 1. Create a full suite of records across models
        InventoryItem.objects.create(
            user=self.user,
            item=self.rifle,
            source='case',
            is_sold=False
        )
        Transaction.objects.create(
            user=self.user,
            amount=Decimal('50.00'),
            transaction_type='deposit',
            status='completed',
            payment_method='telegram'
        )
        promo = PromoCode.objects.create(
            code='MIGRATE100',
            bonus_type='coins',
            bonus_value=Decimal('100.00'),
            starts_at=timezone.now() - timedelta(days=1),
            expires_at=timezone.now() + timedelta(days=7),
            is_active=True
        )
        PersonalCaseChance.objects.create(
            user=self.user,
            case=self.case,
            item=self.rifle,
            chance=Decimal('25.50'),
            starts_at=timezone.now() - timedelta(days=1),
            expires_at=timezone.now() + timedelta(days=7),
            is_active=True
        )

        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tf:
            temp_backup_file = tf.name

        try:
            # 2. Export backup
            call_command('backup_data', output=temp_backup_file)

            # 3. Clean and Restore
            call_command('restore_data', temp_backup_file, clean=True)

            # 4. Verify password authentication succeeds with the original user credentials
            auth_client = Client()
            login_success = auth_client.login(username='SecurityUser', password='StrongPassword123!')
            self.assertTrue(login_success, "User failed to authenticate with original password after restore!")

            # 5. Verify user balance and profile integrity
            restored_user = User.objects.get(username='SecurityUser')
            self.assertEqual(restored_user.profile.balance, Decimal('100.00'))

            # 6. Verify inventory, transaction, promo, and chance models
            self.assertEqual(InventoryItem.objects.filter(user=restored_user).count(), 1)
            self.assertEqual(Transaction.objects.filter(user=restored_user, transaction_type='deposit').count(), 1)
            self.assertEqual(PromoCode.objects.filter(code='MIGRATE100').count(), 1)
            self.assertEqual(PersonalCaseChance.objects.filter(user=restored_user).count(), 1)

            # 7. Run verify_migration with --compare flag
            call_command('verify_migration', compare=temp_backup_file)

        finally:
            if os.path.exists(temp_backup_file):
                os.remove(temp_backup_file)

    def test_media_backup_and_restore_lifecycle(self):
        """Verify media assets archiving and extraction."""
        from django.core.management import call_command
        import tempfile
        from django.conf import settings

        media_root = Path(settings.MEDIA_ROOT)
        media_root.mkdir(parents=True, exist_ok=True)
        test_file = media_root / 'test_avatar.png'
        test_file.write_text('fake_image_content_12345')

        with tempfile.NamedTemporaryFile(suffix='.tar.gz', delete=False) as tf:
            temp_tar_file = tf.name

        try:
            call_command('backup_media', output=temp_tar_file)
            self.assertTrue(os.path.exists(temp_tar_file))

            # Delete file and restore
            if test_file.exists():
                test_file.unlink()

            call_command('restore_media', temp_tar_file)
            self.assertTrue(test_file.exists())
            self.assertEqual(test_file.read_text(), 'fake_image_content_12345')
        finally:
            if os.path.exists(temp_tar_file):
                os.remove(temp_tar_file)
            if test_file.exists():
                test_file.unlink()

    # ==================== UC CURRENCY SYSTEM TESTS ====================
    def test_uc_currency_conversions(self):
        """Verify UC to USD and UZS conversions and formatting."""
        from payments.currency import (
            get_currency_rates, uc_to_usd, uc_to_uzs,
            format_uc, format_usd_approx, format_uzs_approx
        )
        from payments.models import CurrencySetting

        # Default rates (1 UC = 250 UZS, 1 USD = 12000 UZS)
        rates = get_currency_rates()
        self.assertEqual(rates['uc_to_uzs'], Decimal('250.00'))
        self.assertEqual(rates['usd_to_uzs'], Decimal('12000.00'))

        # 60 UC -> $1.25 USD, 15,000 UZS
        self.assertEqual(uc_to_usd(Decimal('60')), Decimal('1.25'))
        self.assertEqual(uc_to_uzs(Decimal('60')), Decimal('15000'))
        self.assertEqual(format_uc(Decimal('60')), '60 UC')
        self.assertEqual(format_usd_approx(Decimal('60')), '≈ $1.25')
        self.assertEqual(format_uzs_approx(Decimal('60')), '≈ 15 000 UZS')

        # Test custom CurrencySetting
        CurrencySetting.objects.all().delete()
        setting = CurrencySetting.objects.create(
            uc_to_uzs=Decimal('300.00'),
            usd_to_uzs=Decimal('12000.00')
        )
        cache.clear()
        updated_rates = get_currency_rates()
        self.assertEqual(updated_rates['uc_to_uzs'], Decimal('300.00'))
        # 60 UC * (300 / 12000) = $1.50
        self.assertEqual(uc_to_usd(Decimal('60')), Decimal('1.50'))

    def test_uc_template_tags(self):
        """Verify template tags render UC badges, icons, and approximations."""
        from cases.templatetags.currency_tags import (
            uc_filter, uc_amount_filter, usd_approx_filter, uzs_approx_filter,
            uc_icon, uc_badge
        )

        self.assertEqual(uc_filter(1800), '1 800 UC')
        self.assertEqual(uc_amount_filter(1800), '1 800')
        self.assertIn('$', usd_approx_filter(60))
        self.assertIn('UZS', uzs_approx_filter(60))

        icon_html = uc_icon(size=20)
        self.assertIn('uc_icon', icon_html)
        self.assertIn('.png', icon_html)
        self.assertIn('width="20"', icon_html)

        badge_html = uc_badge(60, show_usd=True)
        self.assertIn('uc-badge', badge_html)
        self.assertIn('60 UC', badge_html)
        self.assertIn('usd-approx', badge_html)

    def test_smoke_admin_promotion_and_access(self):
        """Verify Smoke is promoted to admin and has full access to /admin/."""
        from django.core.management import call_command

        # Create normal user Smoke
        smoke_user, _ = User.objects.get_or_create(
            username='Smoke',
            defaults={'email': 'smoke@neondrop.gg', 'is_staff': False, 'is_superuser': False}
        )
        smoke_user.is_staff = False
        smoke_user.is_superuser = False
        smoke_user.save()

        # Run command
        call_command('promote_admin', 'Smoke')
        smoke_user.refresh_from_db()
        self.assertTrue(smoke_user.is_staff)
        self.assertTrue(smoke_user.is_superuser)
        self.assertTrue(smoke_user.is_active)

        # Test admin access via client
        client = Client()
        client.force_login(smoke_user)
        response = client.get('/admin/')
        self.assertEqual(response.status_code, 200)

    def test_blogger_promocode_reward_calculation(self):
        """Verify blogger reward is calculated strictly from net loss: Net Loss = Spent - Won."""
        now = timezone.now()
        blogger_promo = PromoCode.objects.create(
            code='BLOGER10',
            blogger_name='YouTube @TopGamer',
            blogger_percentage=Decimal('10.00'),
            bonus_type='coins',
            bonus_value=Decimal('50.00'),
            max_uses=500,
            starts_at=now - timedelta(days=2),
            expires_at=now + timedelta(days=30),
            is_active=True,
        )

        # Referred user activates promo
        ref_user = User.objects.create_user(username='ReferredUser1', password='Password123!')
        PromoCodeUse.objects.create(
            promo_code=blogger_promo,
            user=ref_user,
            bonus_amount=Decimal('50.00'),
            used_at=now - timedelta(hours=5)
        )

        # User opens cases: Spent 1000 UC, Won 160 UC
        win_item = Item.objects.create(name='Won Skin', weapon_type='AWP', skin_name='Special', value=Decimal('160.00'))
        Opening.objects.create(
            user=ref_user,
            case=self.case,
            item=win_item,
            price=Decimal('1000.00'),
            server_seed_hash='hash_test',
            server_seed='seed_test',
            client_seed='client_test',
            nonce=1,
            created_at=now - timedelta(hours=3)
        )

        stats = blogger_promo.get_stats_all_time()
        self.assertEqual(stats['users_count'], 1)
        self.assertEqual(stats['total_spent'], Decimal('1000.00'))
        self.assertEqual(stats['total_won'], Decimal('160.00'))
        self.assertEqual(stats['net_loss'], Decimal('840.00'))
        self.assertEqual(stats['blogger_percentage'], Decimal('10.00'))
        self.assertEqual(stats['blogger_payout'], Decimal('84.00'))
        self.assertEqual(stats['site_revenue'], Decimal('756.00'))

    def test_independent_promocode_percentages(self):
        """Verify multiple promocodes calculate their blogger rewards independently."""
        now = timezone.now()
        promo_a = PromoCode.objects.create(
            code='PROMO_A_10',
            blogger_percentage=Decimal('10.00'),
            bonus_type='coins',
            bonus_value=Decimal('10.00'),
            starts_at=now - timedelta(days=1),
            expires_at=now + timedelta(days=30),
        )
        promo_b = PromoCode.objects.create(
            code='PROMO_B_25',
            blogger_percentage=Decimal('25.00'),
            bonus_type='coins',
            bonus_value=Decimal('10.00'),
            starts_at=now - timedelta(days=1),
            expires_at=now + timedelta(days=30),
        )

        user_a = User.objects.create_user(username='UserA', password='Password123!')
        user_b = User.objects.create_user(username='UserB', password='Password123!')

        PromoCodeUse.objects.create(promo_code=promo_a, user=user_a, used_at=now - timedelta(hours=4))
        PromoCodeUse.objects.create(promo_code=promo_b, user=user_b, used_at=now - timedelta(hours=4))

        win_skin = Item.objects.create(name='Skin', weapon_type='AK-47', skin_name='Skin', value=Decimal('200.00'))
        # User A: Spent 500, Won 200 -> Loss 300, 10% = 30 UC
        Opening.objects.create(
            user=user_a, case=self.case, item=win_skin, price=Decimal('500.00'),
            server_seed_hash='hA', server_seed='sA', client_seed='cA', nonce=1
        )
        # User B: Spent 600, Won 200 -> Loss 400, 25% = 100 UC
        Opening.objects.create(
            user=user_b, case=self.case, item=win_skin, price=Decimal('600.00'),
            server_seed_hash='hB', server_seed='sB', client_seed='cB', nonce=2
        )

        stats_a = promo_a.get_stats_all_time()
        stats_b = promo_b.get_stats_all_time()

        self.assertEqual(stats_a['net_loss'], Decimal('300.00'))
        self.assertEqual(stats_a['blogger_payout'], Decimal('30.00'))
        self.assertEqual(stats_a['site_revenue'], Decimal('270.00'))

        self.assertEqual(stats_b['net_loss'], Decimal('400.00'))
        self.assertEqual(stats_b['blogger_payout'], Decimal('100.00'))
        self.assertEqual(stats_b['site_revenue'], Decimal('300.00'))

    def test_blogger_admin_dashboard_rendering(self):
        """Verify Admin renders blogger metrics, daily table, and date filters without error."""
        now = timezone.now()
        promo = PromoCode.objects.create(
            code='ADMIN_TEST_PROMO',
            blogger_name='StreamerX',
            blogger_percentage=Decimal('15.00'),
            bonus_type='coins',
            bonus_value=Decimal('20.00'),
            starts_at=now - timedelta(days=2),
            expires_at=now + timedelta(days=30),
        )

        self.client.force_login(self.admin_user)
        res_list = self.client.get('/admin/cases/promocode/')
        self.assertEqual(res_list.status_code, 200)
        self.assertContains(res_list, 'ADMIN_TEST_PROMO')
        self.assertContains(res_list, '15.00%')

        res_change = self.client.get(f'/admin/cases/promocode/{promo.id}/change/')
        self.assertEqual(res_change.status_code, 200)
        self.assertContains(res_change, 'Финансовая статистика промокода')
        self.assertContains(res_change, 'Детализация расчётов по дням')
        self.assertContains(res_change, 'К выплате блогеру')
        self.assertContains(res_change, 'Доход сайта')

    def test_deploy_and_migration_preserves_custom_cases_and_deletions(self):
        """
        Verify that creating a custom case, modifying an existing case, and deleting an old case
        are 100% persistent and never reverted by migrate, wsgi startup, or deploy scripts.
        """
        # 1. Create a custom case as if created in Django Admin
        custom_case = Case.objects.create(
            name='TEST_NEW_CASE',
            slug='test-new-case',
            price=Decimal('77.50'),
            color_theme='demon-orange',
            active=True,
            is_popular=True,
        )
        custom_item = Item.objects.create(
            weapon_type='AWP',
            skin_name='Custom Hyper',
            value=Decimal('350.00'),
            rarity='covert',
        )
        CaseItem.objects.create(case=custom_case, item=custom_item, weight=100.0)

        # 2. Modify an existing case
        self.case.price = Decimal('999.00')
        self.case.color_theme = 'godlike-gold'
        self.case.save()

        # 3. Create a temporary case and delete it
        old_case = Case.objects.create(
            name='OLD_DELETED_CASE',
            slug='old-deleted-case',
            price=Decimal('12.00'),
            color_theme='frost-cyan',
        )
        old_case_id = old_case.id
        old_case.delete()

        # 4. Simulate what runs during a Deploy / Server Restart:
        #    a) python manage.py migrate --noinput
        #    b) python manage.py promote_admin Smoke
        #    c) WSGI boot
        from django.core.management import call_command
        call_command('migrate', interactive=False)
        call_command('promote_admin', 'Smoke')

        # 5. Verify database state post-deploy:
        # - TEST_NEW_CASE must still exist exactly as configured
        reloaded_custom = Case.objects.filter(slug='test-new-case').first()
        self.assertIsNotNone(reloaded_custom)
        self.assertEqual(reloaded_custom.name, 'TEST_NEW_CASE')
        self.assertEqual(reloaded_custom.price, Decimal('77.50'))
        self.assertEqual(reloaded_custom.color_theme, 'demon-orange')
        self.assertEqual(reloaded_custom.case_items.count(), 1)

        # - Deleted case must NOT have been restored
        self.assertFalse(Case.objects.filter(slug='old-deleted-case').exists())

        # - Modified case must keep its updated price and theme
        reloaded_existing = Case.objects.get(id=self.case.id)
        self.assertEqual(reloaded_existing.price, Decimal('999.00'))
        self.assertEqual(reloaded_existing.color_theme, 'godlike-gold')

    def test_full_user_and_case_persistence_across_deploy(self):
        """
        Complete end-to-end verification:
        1. User registers, logs in, holds balance, owns inventory, performs transactions.
        2. Admin creates custom cases and deletes old cases.
        3. Deploy lifecycle executes (migrate, promote_admin, wsgi boot).
        4. User, password hash, permissions, balances, inventory, and cases remain 100% untouched.
        """
        from django.contrib.auth import authenticate
        from django.core.management import call_command
        from payments.models import Transaction

        # 1. Create a user with password and balance
        raw_password = 'MySecretSecurePass99!'
        user = User.objects.create_user(
            username='PlayerAlice',
            email='alice@neondrop.gg',
            password=raw_password,
        )
        user.profile.balance = Decimal('550.00')
        user.profile.save()

        # 2. Add inventory item and transaction
        inv_item = InventoryItem.objects.create(
            user=user,
            item=self.knife,
            source='case',
            is_sold=False,
        )
        tx = Transaction.objects.create(
            user=user,
            amount=Decimal('100.00'),
            transaction_type='deposit',
            status='completed',
            balance_after=Decimal('550.00'),
        )

        # 3. Create a custom case and delete an old case
        new_case = Case.objects.create(
            name='ADMIN_LIVE_CASE',
            slug='admin-live-case',
            price=Decimal('15.00'),
            color_theme='neon-green',
        )
        to_delete_case = Case.objects.create(
            name='OLD_UNUSED_CASE',
            slug='old-unused-case',
            price=Decimal('5.00'),
            color_theme='cyber-pink',
        )
        to_delete_case.delete()

        # 4. Simulate Deploy / Container Restart
        call_command('migrate', interactive=False)
        call_command('promote_admin', 'Smoke')

        # 5. Verify User and Authentication
        reloaded_user = User.objects.filter(username='PlayerAlice').first()
        self.assertIsNotNone(reloaded_user)
        self.assertEqual(reloaded_user.email, 'alice@neondrop.gg')
        self.assertTrue(reloaded_user.check_password(raw_password))

        authenticated_user = authenticate(username='PlayerAlice', password=raw_password)
        self.assertIsNotNone(authenticated_user)
        self.assertEqual(authenticated_user.id, user.id)

        # Verify balance, inventory, and transactions
        self.assertEqual(reloaded_user.profile.balance, Decimal('550.00'))
        self.assertEqual(InventoryItem.objects.filter(user=reloaded_user, is_sold=False).count(), 1)
        self.assertEqual(Transaction.objects.filter(user=reloaded_user).count(), 1)

        # Verify Cases
        self.assertTrue(Case.objects.filter(slug='admin-live-case').exists())
        self.assertFalse(Case.objects.filter(slug='old-unused-case').exists())





