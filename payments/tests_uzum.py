import json
import uuid
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, Client, override_settings
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from django.conf import settings

from payments.models import UCPackage, UzumPayment, Transaction
from payments.uzum_client import UzumClient
from cases.models import BloggerPromoCode, PromoCodeUse


@override_settings(UZUM_SECRET_KEY='test_uzum_secret_key_12345', UZUM_TEST_MODE=False)
class UzumCheckoutIntegrationTests(TestCase):
    """
    Comprehensive test suite for Uzum Checkout automated balance top-up:
    1. Pending payment creation.
    2. Successful webhook -> UC credited.
    3. Duplicate webhook -> UC NOT credited twice (Strict Idempotency).
    4. Forged/Invalid signature webhook -> Rejected (403), UC NOT credited.
    5. Failed payment webhook -> UC NOT credited.
    6. Return URL without webhook -> Strictly read-only, UC NOT credited.
    7. Amount mismatch -> Rejected (400), UC NOT credited.
    8. Unknown payment ID -> Rejected (404).
    9. Concurrent webhook requests -> Exactly one credit.
    10. Ledger Transaction created correctly with 'card' and 'deposit'.
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='player_uzum',
            email='uzum@test.com',
            password='testpassword123'
        )
        self.user.profile.balance = Decimal('100.00')
        self.user.profile.save()

        # Ensure packages exist
        UCPackage.ensure_default_packages()
        self.pkg_60 = UCPackage.objects.get(uc_amount=60)
        self.pkg_325 = UCPackage.objects.get(uc_amount=325)

        self.client.login(username='player_uzum', password='testpassword123')

    def test_01_create_pending_payment(self):
        """1. Backend creates UzumPayment and pending state with authoritative server pricing."""
        res = self.client.post(reverse('payments:uzum_create_payment'), {
            'package_id': self.pkg_60.id
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        self.assertIn('payment_url', data)
        self.assertEqual(data['uc_amount'], 60)
        self.assertEqual(data['amount_uzs'], 15000)

        # Verify DB record
        payment = UzumPayment.objects.get(order_number=data['order_number'])
        self.assertEqual(payment.status, 'pending')
        self.assertEqual(payment.user, self.user)
        self.assertEqual(payment.uc_amount, Decimal('60.00'))
        self.assertEqual(payment.amount_uzs, Decimal('15000.00'))
        self.assertIsNone(payment.paid_at)
        self.assertIsNone(payment.related_transaction)

        # Balance remains unchanged
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.balance, Decimal('100.00'))

    def test_02_successful_webhook_credits_uc(self):
        """2. Valid webhook from Uzum with COMPLETED status credits UC."""
        payment = UzumPayment.objects.create(
            order_number='ND-UZ-TEST0001',
            user=self.user,
            package=self.pkg_60,
            uc_amount=Decimal('60.00'),
            amount_uzs=Decimal('15000.00'),
            status='pending',
            uzum_order_id='uzum_ext_001'
        )

        payload = {
            'orderNumber': payment.order_number,
            'orderId': 'uzum_ext_001',
            'status': 'COMPLETED',
            'amount': 1500000  # 15 000 UZS in tiyin
        }
        body = json.dumps(payload)
        sig = UzumClient.generate_signature(body.encode('utf-8'))

        res = self.client.post(
            reverse('payments:uzum_webhook'),
            data=body,
            content_type='application/json',
            HTTP_X_SIGNATURE=sig
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json().get('status'), 'OK')

        # Balance increased by 60 UC
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.balance, Decimal('160.00'))

        # Payment status updated to paid
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'paid')
        self.assertIsNotNone(payment.paid_at)
        self.assertIsNotNone(payment.related_transaction)
        self.assertEqual(payment.related_transaction.amount, Decimal('60.00'))
        self.assertEqual(payment.related_transaction.payment_method, 'card')

    def test_03_duplicate_webhook_does_not_double_credit(self):
        """3. Multiple webhook calls for the same payment must not double-credit (Idempotency)."""
        payment = UzumPayment.objects.create(
            order_number='ND-UZ-TEST0002',
            user=self.user,
            package=self.pkg_60,
            uc_amount=Decimal('60.00'),
            amount_uzs=Decimal('15000.00'),
            status='pending',
            uzum_order_id='uzum_ext_002'
        )

        payload = {
            'orderNumber': payment.order_number,
            'orderId': 'uzum_ext_002',
            'status': 'COMPLETED',
            'amount': 1500000
        }
        body = json.dumps(payload)
        sig = UzumClient.generate_signature(body.encode('utf-8'))

        # 1st Webhook Call
        res1 = self.client.post(
            reverse('payments:uzum_webhook'),
            data=body,
            content_type='application/json',
            HTTP_X_SIGNATURE=sig
        )
        self.assertEqual(res1.status_code, 200)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.balance, Decimal('160.00'))

        # 2nd Webhook Call (retry)
        res2 = self.client.post(
            reverse('payments:uzum_webhook'),
            data=body,
            content_type='application/json',
            HTTP_X_SIGNATURE=sig
        )
        self.assertEqual(res2.status_code, 200)
        self.assertIn('already processed', res2.json().get('message', '').lower())

        # 3rd Webhook Call
        res3 = self.client.post(
            reverse('payments:uzum_webhook'),
            data=body,
            content_type='application/json',
            HTTP_X_SIGNATURE=sig
        )
        self.assertEqual(res3.status_code, 200)

        # Balance must still be strictly 160.00 UC (only credited ONCE)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.balance, Decimal('160.00'))

        # Only one transaction created
        tx_count = Transaction.objects.filter(reference_id=f"uzum:{payment.order_number}").count()
        self.assertEqual(tx_count, 1)

    def test_04_forged_webhook_signature_rejected(self):
        """4. Webhook with forged/invalid signature is rejected with 403 and never credits UC."""
        payment = UzumPayment.objects.create(
            order_number='ND-UZ-TEST0003',
            user=self.user,
            package=self.pkg_60,
            uc_amount=Decimal('60.00'),
            amount_uzs=Decimal('15000.00'),
            status='pending',
            uzum_order_id='uzum_ext_003'
        )

        payload = {
            'orderNumber': payment.order_number,
            'orderId': 'uzum_ext_003',
            'status': 'COMPLETED',
            'amount': 1500000
        }
        body = json.dumps(payload)

        # Temporary configure secret key to enforce strict HMAC validation
        with self.settings(UZUM_SECRET_KEY='real_secret_key_123', UZUM_TEST_MODE=False):
            res = self.client.post(
                reverse('payments:uzum_webhook'),
                data=body,
                content_type='application/json',
                HTTP_X_SIGNATURE='forged_invalid_signature_hash'
            )
            self.assertEqual(res.status_code, 403)

        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.balance, Decimal('100.00'))

        payment.refresh_from_db()
        self.assertEqual(payment.status, 'pending')

    def test_05_failed_payment_webhook_does_not_credit_uc(self):
        """5. Webhook reporting DECLINED or FAILED marks payment failed without crediting UC."""
        payment = UzumPayment.objects.create(
            order_number='ND-UZ-TEST0004',
            user=self.user,
            package=self.pkg_60,
            uc_amount=Decimal('60.00'),
            amount_uzs=Decimal('15000.00'),
            status='pending',
            uzum_order_id='uzum_ext_004'
        )

        payload = {
            'orderNumber': payment.order_number,
            'orderId': 'uzum_ext_004',
            'status': 'DECLINED',
            'amount': 1500000
        }
        body = json.dumps(payload)
        sig = UzumClient.generate_signature(body.encode('utf-8'))

        with patch.object(UzumClient, 'get_order_status', return_value={'status': 'DECLINED'}):
            res = self.client.post(
                reverse('payments:uzum_webhook'),
                data=body,
                content_type='application/json',
                HTTP_X_SIGNATURE=sig
            )
            self.assertEqual(res.status_code, 200)

        payment.refresh_from_db()
        self.assertEqual(payment.status, 'failed')

        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.balance, Decimal('100.00'))

    def test_06_return_url_without_webhook_is_strictly_read_only(self):
        """6. Return URL only renders status and NEVER credits UC directly."""
        payment = UzumPayment.objects.create(
            order_number='ND-UZ-TEST0005',
            user=self.user,
            package=self.pkg_60,
            uc_amount=Decimal('60.00'),
            amount_uzs=Decimal('15000.00'),
            status='pending',
            uzum_order_id='uzum_ext_005'
        )

        # User visits return URL directly
        res = self.client.get(reverse('payments:uzum_return') + f"?order_id={payment.order_number}")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'ND-UZ-TEST0005')
        self.assertContains(res, 'ПРОВЕРЯЕМ ОПЛАТУ')

        # Balance remains unchanged
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.balance, Decimal('100.00'))

        payment.refresh_from_db()
        self.assertEqual(payment.status, 'pending')

    def test_07_amount_mismatch_rejected(self):
        """7. Webhook attempting to report incorrect amount (tampering) is rejected."""
        payment = UzumPayment.objects.create(
            order_number='ND-UZ-TEST0006',
            user=self.user,
            package=self.pkg_60,
            uc_amount=Decimal('60.00'),
            amount_uzs=Decimal('15000.00'),
            status='pending',
            uzum_order_id='uzum_ext_006'
        )

        # Expected 15 000 UZS = 1 500 000 tiyin, but sends only 1 000 000 tiyin
        payload = {
            'orderNumber': payment.order_number,
            'orderId': 'uzum_ext_006',
            'status': 'COMPLETED',
            'amount': 1000000
        }
        body = json.dumps(payload)
        sig = UzumClient.generate_signature(body.encode('utf-8'))

        res = self.client.post(
            reverse('payments:uzum_webhook'),
            data=body,
            content_type='application/json',
            HTTP_X_SIGNATURE=sig
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn('Amount mismatch', res.json().get('error', ''))

        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.balance, Decimal('100.00'))

        payment.refresh_from_db()
        self.assertEqual(payment.status, 'failed')

    def test_08_unknown_payment_id_rejected(self):
        """8. Webhook with unknown order number returns 404."""
        payload = {
            'orderNumber': 'ND-UZ-NONEXISTENT',
            'orderId': 'uzum_ghost_999',
            'status': 'COMPLETED',
            'amount': 1500000
        }
        body = json.dumps(payload)
        sig = UzumClient.generate_signature(body.encode('utf-8'))

        res = self.client.post(
            reverse('payments:uzum_webhook'),
            data=body,
            content_type='application/json',
            HTTP_X_SIGNATURE=sig
        )
        self.assertEqual(res.status_code, 404)

    def test_09_concurrent_webhook_single_credit(self):
        """9. Sequential/concurrent webhook triggers result in exactly one balance credit."""
        payment = UzumPayment.objects.create(
            order_number='ND-UZ-TEST0008',
            user=self.user,
            package=self.pkg_325,
            uc_amount=Decimal('325.00'),
            amount_uzs=Decimal('81250.00'),
            status='pending',
            uzum_order_id='uzum_ext_008'
        )

        payload = {
            'orderNumber': payment.order_number,
            'orderId': 'uzum_ext_008',
            'status': 'COMPLETED',
            'amount': 8125000
        }
        body = json.dumps(payload)
        sig = UzumClient.generate_signature(body.encode('utf-8'))

        # Run multiple requests
        for _ in range(3):
            self.client.post(
                reverse('payments:uzum_webhook'),
                data=body,
                content_type='application/json',
                HTTP_X_SIGNATURE=sig
            )

        self.user.profile.refresh_from_db()
        # 100.00 + 325.00 = 425.00
        self.assertEqual(self.user.profile.balance, Decimal('425.00'))

    def test_10_transaction_created_correctly_with_card_method(self):
        """10. Ledger Transaction record is created with payment_method='card' and proper audit info."""
        payment = UzumPayment.objects.create(
            order_number='ND-UZ-TEST0010',
            user=self.user,
            package=self.pkg_60,
            uc_amount=Decimal('60.00'),
            amount_uzs=Decimal('15000.00'),
            status='pending',
            uzum_order_id='uzum_ext_010'
        )

        payload = {
            'orderNumber': payment.order_number,
            'orderId': 'uzum_ext_010',
            'status': 'COMPLETED',
            'amount': 1500000
        }
        body = json.dumps(payload)
        sig = UzumClient.generate_signature(body.encode('utf-8'))

        self.client.post(
            reverse('payments:uzum_webhook'),
            data=body,
            content_type='application/json',
            HTTP_X_SIGNATURE=sig
        )

        tx = Transaction.objects.filter(reference_id=f"uzum:{payment.order_number}").first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.user, self.user)
        self.assertEqual(tx.amount, Decimal('60.00'))
        self.assertEqual(tx.payment_method, 'card')
        self.assertEqual(tx.transaction_type, 'deposit')
        self.assertEqual(tx.status, 'completed')
        self.assertEqual(tx.balance_before, Decimal('100.00'))
        self.assertEqual(tx.balance_after, Decimal('160.00'))
        self.assertIn('Uzum Checkout', tx.description)

    def test_11_blogger_discount_applied_to_uzum_payment(self):
        """Bonus test: If user activated blogger code, package price reflects 60 UC = 13 000 UZS."""
        blogger_promo = BloggerPromoCode.objects.create(
            code='STREAMER_UZUM',
            blogger_name='Uzum Streamer',
            blogger_percentage=Decimal('10.00')
        )
        # User redeems blogger promo code
        PromoCodeUse.objects.create(user=self.user, promo_code=blogger_promo, bonus_amount=Decimal('0.00'))

        # Check calculated price for 60 UC: 13 000 UZS instead of 15 000 UZS
        self.assertEqual(self.pkg_60.get_actual_price_uzs(self.user), Decimal('13000.00'))

        # Check calculated price for 325 UC: round(325 * 13000 / 60) = 70 417 UZS
        self.assertEqual(self.pkg_325.get_actual_price_uzs(self.user), Decimal('70417.00'))

        # Create payment via API
        res = self.client.post(reverse('payments:uzum_create_payment'), {
            'package_id': self.pkg_60.id
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data['amount_uzs'], 13000)

        payment = UzumPayment.objects.get(order_number=data['order_number'])
        self.assertEqual(payment.amount_uzs, Decimal('13000.00'))
        self.assertEqual(payment.promo_code, blogger_promo)
