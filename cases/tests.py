from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.core.cache import cache
from decimal import Decimal
import json

from cases.models import Case, Item, CaseItem, Opening
from inventory.models import InventoryItem
from payments.models import Transaction
from payments.services import modify_user_balance
from payments.admin import approve_deposits
from cases.provably_fair import calculate_provably_fair_roll, hash_seed, generate_server_seed

class NeonDropSecurityTests(TestCase):
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

    def test_unauthorized_case_opening_rejected(self):
        """Unauthenticated user cannot open cases."""
        response = self.client.post(reverse('cases:open_case_api', kwargs={'slug': self.case.slug}))
        self.assertEqual(response.status_code, 302)  # Redirects to login
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

        # Balance remains unchanged
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('5.00'))
        self.assertEqual(Opening.objects.count(), 0)
        self.assertEqual(InventoryItem.objects.count(), 0)

    def test_client_tampering_ignored(self):
        """Client sending fake price or fake item is ignored; authoritative DB price and server roll are used."""
        self.client.login(username='SecurityUser', password='StrongPassword123!')
        
        # Malicious client sends fake price and fake item
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

        # Verified that authoritative price $10.00 was deducted, not fake $0.01
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('90.00'))

        # Verified ledger record created
        tx = Transaction.objects.filter(user=self.user, transaction_type='case_open').latest('created_at')
        self.assertEqual(tx.amount, Decimal('-10.00'))
        self.assertEqual(tx.balance_before, Decimal('100.00'))
        self.assertEqual(tx.balance_after, Decimal('90.00'))

    def test_idempotency_duplicate_prevention(self):
        """Duplicate request with same idempotency key is rejected."""
        self.client.login(username='SecurityUser', password='StrongPassword123!')
        idempotency_key = 'unique_request_uuid_999'

        # First request succeeds
        res1 = self.client.post(
            reverse('cases:open_case_api', kwargs={'slug': self.case.slug}),
            {'idempotency_key': idempotency_key}
        )
        self.assertEqual(res1.status_code, 200)

        # Immediate replay / double click fails with 409 Conflict
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
        """Second sell attempt on an already sold item is rejected (double-spending protection)."""
        user_item = InventoryItem.objects.create(user=self.user, item=self.pistol, source='case')
        self.client.login(username='SecurityUser', password='StrongPassword123!')

        # First sell succeeds
        res1 = self.client.post(reverse('inventory:sell_item', kwargs={'item_id': user_item.id}))
        self.assertEqual(res1.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('118.73'))

        # Second sell fails
        res2 = self.client.post(reverse('inventory:sell_item', kwargs={'item_id': user_item.id}))
        self.assertEqual(res2.status_code, 400)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('118.73'))  # Unchanged

    def test_deposit_flow_requires_admin_approval(self):
        """Deposit creation does not alter balance automatically; admin approval credits balance atomically."""
        self.client.login(username='SecurityUser', password='StrongPassword123!')
        
        # Negative / Zero amounts are rejected
        res_neg = self.client.post(reverse('payments:create_request'), {'amount': '-25'})
        self.assertEqual(res_neg.status_code, 400)
        res_zero = self.client.post(reverse('payments:create_request'), {'amount': '0'})
        self.assertEqual(res_zero.status_code, 400)

        # 1. Create deposit request for $50.00
        res = self.client.post(reverse('payments:create_request'), {'amount': '50'})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        self.assertIn('telegram_url', data)
        self.assertIn('https://t.me/neondrop_admin?text=', data['telegram_url'])
        
        import urllib.parse
        decoded_url = urllib.parse.unquote(data['telegram_url'])
        self.assertIn("Здравствуйте! Хочу пополнить баланс NEONDROP.", decoded_url)
        self.assertIn("Мой логин: SecurityUser", decoded_url)
        self.assertIn(f"Мой ID: {self.user.id}", decoded_url)
        self.assertIn("Сумма пополнения: $50", decoded_url)
        
        tx_id = data['transaction_id']

        # Balance remains unchanged at this stage
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('100.00'))
        
        tx = Transaction.objects.get(id=tx_id)
        self.assertEqual(tx.status, 'pending')

        # 2. Admin approves deposit
        approve_deposits(None, type('Req', (), {'user': self.admin_user})(), Transaction.objects.filter(id=tx_id))
        
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('150.00'))
        tx.refresh_from_db()
        self.assertEqual(tx.status, 'completed')

    def test_provably_fair_verification(self):
        """Provably fair HMAC-SHA256 roll calculation is deterministic and mathematically bounded [0.0, 1.0)."""
        server_seed = generate_server_seed()
        client_seed = "client_entropy_456"
        nonce = 1

        roll1 = calculate_provably_fair_roll(server_seed, client_seed, nonce)
        roll2 = calculate_provably_fair_roll(server_seed, client_seed, nonce)

        self.assertEqual(roll1, roll2)
        self.assertGreaterEqual(roll1, 0.0)
        self.assertLess(roll1, 1.0)
        self.assertEqual(hash_seed(server_seed), hash_seed(server_seed))
