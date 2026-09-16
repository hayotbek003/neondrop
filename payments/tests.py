import urllib.parse
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse

from django.core.cache import cache

from payments.models import Transaction, Withdrawal
from users.models import Profile, AdminPermissionProfile


class WithdrawalSystemTestCase(TestCase):
    """
    Comprehensive test suite covering all requirements of the NEONDROP withdrawal system:
    1. Authorized user sees "Вывести" button in UI.
    2. Unauthorized user does NOT see "Вывести" button in UI.
    3. Creation of withdrawal request immediately deducts UC and creates pending Withdrawal record.
    4. Telegram URL contains user ID, username, amount UC, method, details, balance after, date and status.
    5. Strict validations: minimum 60 UC, integer UC only, positive amount, balance check.
    6. Admin approve/complete does NOT deduct balance a second time.
    7. Admin reject automatically refunds deducted UC and creates refund transaction.
    8. Repeated processing is idempotent (cannot double deduct or double refund).
    9. Bulk actions work properly.
    10. Existing deposit system remains fully functional.
    """

    def setUp(self):
        cache.clear()
        self.client = Client()

        # Create regular user
        self.user = User.objects.create_user(
            username='player_one',
            password='password123',
            email='player_one@neondrop.gg'
        )
        self.profile, _ = Profile.objects.get_or_create(user=self.user)
        self.profile.balance = Decimal('150.00')
        self.profile.save()

        # Create admin user
        self.admin = User.objects.create_superuser(
            username='boss_admin',
            password='adminpassword',
            email='admin@neondrop.gg'
        )
        self.admin_profile, _ = Profile.objects.get_or_create(user=self.admin)
        self.admin_profile.balance = Decimal('500.00')
        self.admin_profile.save()

    def test_01_authorized_user_sees_withdraw_button(self):
        """1. Авторизованный пользователь видит кнопку «Вывести» и модальное окно."""
        self.client.login(username='player_one', password='password123')
        resp = self.client.get(reverse('cases:home'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Вывести')
        self.assertContains(resp, 'open-withdraw-modal-trigger')
        self.assertContains(resp, 'withdrawalModal')
        self.assertContains(resp, 'ВЫВОД UC')

    def test_02_unauthorized_user_does_not_see_withdraw_button(self):
        """2. Неавторизованный пользователь НЕ видит кнопку «Вывести»."""
        self.client.logout()
        resp = self.client.get(reverse('cases:home'))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'open-withdraw-modal-trigger')
        self.assertNotContains(resp, 'withdrawalModal')

    def test_03_create_withdrawal_and_immediate_balance_deduction(self):
        """3. UC списываются СРАЗУ при создании заявки; заявка получает pending."""
        self.client.login(username='player_one', password='password123')
        initial_balance = Decimal('150.00')
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, initial_balance)

        payload = {
            'amount': '70',
            'method': 'PUBG Mobile (по ID игрока)',
            'details': 'ID: 5123456789, Nick: NeonSniper'
        }
        resp = self.client.post(reverse('payments:create_withdrawal'), data=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertIn('withdrawal_id', data)
        self.assertEqual(data['balance_after'], '80')

        # Check user balance is immediately deducted: 150 - 70 = 80
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('80.00'))

        # Check Withdrawal record
        w = Withdrawal.objects.get(id=data['withdrawal_id'])
        self.assertEqual(w.user, self.user)
        self.assertEqual(w.username, 'player_one')
        self.assertEqual(w.user_id_val, self.user.id)
        self.assertEqual(w.amount, Decimal('70.00'))
        self.assertEqual(w.amount_uc, 70)
        self.assertEqual(w.method, 'PUBG Mobile (по ID игрока)')
        self.assertEqual(w.details, 'ID: 5123456789, Nick: NeonSniper')
        self.assertEqual(w.status, 'pending')

        # Check Transaction record
        tx = w.related_transaction
        self.assertIsNotNone(tx)
        self.assertEqual(tx.amount, Decimal('-70.00'))
        self.assertEqual(tx.balance_before, Decimal('150.00'))
        self.assertEqual(tx.balance_after, Decimal('80.00'))
        self.assertEqual(tx.transaction_type, 'withdraw')
        self.assertEqual(tx.status, 'completed')

    def test_04_telegram_url_content_and_encoding(self):
        """4. Telegram URL содержит все обязательные поля с правильным URL encoding."""
        self.client.login(username='player_one', password='password123')
        payload = {
            'amount': '65',
            'method': 'Telegram',
            'details': '@my_telegram_tag'
        }
        resp = self.client.post(reverse('payments:create_withdrawal'), data=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        tg_url = data['telegram_url']

        self.assertTrue(tg_url.startswith('https://t.me/neondrop_admin?text='))
        parsed = urllib.parse.urlparse(tg_url)
        params = urllib.parse.parse_qs(parsed.query)
        self.assertIn('text', params)
        decoded_text = params['text'][0]

        # Verify exact required fields
        self.assertIn('🔔 НОВЫЙ ВЫВОД NEONDROP', decoded_text)
        self.assertIn(f'Заявка №: {data["withdrawal_id"]}', decoded_text)
        self.assertIn(f'👤 Пользователь: {self.user.username}', decoded_text)
        self.assertIn(f'🆔 ID: {self.user.id}', decoded_text)
        self.assertIn('💰 Сумма: 65 UC', decoded_text)
        self.assertIn('📤 Способ получения:\nTelegram', decoded_text)
        self.assertIn('📋 Реквизиты:\n@my_telegram_tag', decoded_text)
        self.assertIn('💳 Баланс после вывода:\n85 UC', decoded_text)
        self.assertIn('📅 Дата:', decoded_text)
        self.assertIn('Статус: ОЖИДАЕТ ВЫПЛАТЫ', decoded_text)

    def test_05_amount_validations(self):
        """5. Серверная валидация суммы: минимум 60 UC, целое число, > 0, <= баланса."""
        self.client.login(username='player_one', password='password123')

        # 1. Less than 60 UC (59 UC) -> rejected
        resp_59 = self.client.post(reverse('payments:create_withdrawal'), data={
            'amount': '59',
            'method': 'Telegram',
            'details': 'user_tg'
        })
        self.assertEqual(resp_59.status_code, 400)
        self.assertIn('Минимальная сумма вывода — 60 UC.', resp_59.json()['error'])

        # 2. Zero amount -> rejected
        resp_zero = self.client.post(reverse('payments:create_withdrawal'), data={
            'amount': '0',
            'method': 'Telegram',
            'details': 'user_tg'
        })
        self.assertEqual(resp_zero.status_code, 400)

        # 3. Negative amount -> rejected
        resp_neg = self.client.post(reverse('payments:create_withdrawal'), data={
            'amount': '-60',
            'method': 'Telegram',
            'details': 'user_tg'
        })
        self.assertEqual(resp_neg.status_code, 400)

        # 4. Fractional amount (60.5 UC) -> rejected (only integer UC allowed)
        resp_frac = self.client.post(reverse('payments:create_withdrawal'), data={
            'amount': '60.5',
            'method': 'Telegram',
            'details': 'user_tg'
        })
        self.assertEqual(resp_frac.status_code, 400)
        self.assertIn('целым числом', resp_frac.json()['error'])

        # 5. More than user balance (150 UC) -> rejected
        resp_excess = self.client.post(reverse('payments:create_withdrawal'), data={
            'amount': '151',
            'method': 'Telegram',
            'details': 'user_tg'
        })
        self.assertEqual(resp_excess.status_code, 400)
        self.assertIn('Недостаточно средств', resp_excess.json()['error'])

        # 6. Exactly 60 UC -> allowed!
        resp_60 = self.client.post(reverse('payments:create_withdrawal'), data={
            'amount': '60',
            'method': 'Telegram',
            'details': 'user_tg'
        })
        self.assertEqual(resp_60.status_code, 200)
        self.assertTrue(resp_60.json()['success'])

    def test_06_admin_approve_does_not_deduct_balance_again(self):
        """6. Одобрение админом (completed) НЕ списывает баланс второй раз."""
        self.client.login(username='player_one', password='password123')

        # User creates withdrawal for 60 UC
        resp = self.client.post(reverse('payments:create_withdrawal'), data={
            'amount': '60',
            'method': 'Telegram',
            'details': 'tg_user'
        })
        self.assertEqual(resp.status_code, 200)
        wid = resp.json()['withdrawal_id']

        # Balance right after creation: 150 - 60 = 90
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('90.00'))

        # Admin logs in and approves/completes
        self.client.login(username='boss_admin', password='adminpassword')
        approve_url = reverse('admin:payments_withdrawal_approve', args=[wid])
        resp_admin = self.client.get(approve_url, follow=True)
        self.assertEqual(resp_admin.status_code, 200)

        w = Withdrawal.objects.get(id=wid)
        self.assertEqual(w.status, 'completed')
        self.assertEqual(w.processed_by, self.admin)

        # Balance must REMAIN 90.00 (NOT deducted again!)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('90.00'))

    def test_07_admin_reject_automatically_refunds_uc(self):
        """7. Отклонение заявки админом (rejected) автоматически возвращает UC на баланс."""
        self.client.login(username='player_one', password='password123')

        # User creates withdrawal for 80 UC
        resp = self.client.post(reverse('payments:create_withdrawal'), data={
            'amount': '80',
            'method': 'Telegram',
            'details': 'invalid_account'
        })
        self.assertEqual(resp.status_code, 200)
        wid = resp.json()['withdrawal_id']

        # Balance was immediately deducted: 150 - 80 = 70
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('70.00'))

        # Admin rejects
        self.client.login(username='boss_admin', password='adminpassword')
        reject_url = reverse('admin:payments_withdrawal_reject', args=[wid])
        resp_reject = self.client.get(reject_url, follow=True)
        self.assertEqual(resp_reject.status_code, 200)

        w = Withdrawal.objects.get(id=wid)
        self.assertEqual(w.status, 'rejected')
        self.assertEqual(w.processed_by, self.admin)

        # Balance must be automatically restored: 70 + 80 = 150
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('150.00'))

        # Distinct refund transaction created
        refund_tx = Transaction.objects.get(reference_id=f'withdrawal_refund:{wid}')
        self.assertEqual(refund_tx.user, self.user)
        self.assertEqual(refund_tx.amount, Decimal('80.00'))
        self.assertEqual(refund_tx.balance_before, Decimal('70.00'))
        self.assertEqual(refund_tx.balance_after, Decimal('150.00'))
        self.assertEqual(refund_tx.status, 'completed')

    def test_08_repeated_processing_is_idempotent(self):
        """8. Повторная обработка не списывает и не возвращает UC повторно."""
        self.client.login(username='player_one', password='password123')

        # Create withdrawal for 60 UC (balance: 150 -> 90)
        resp = self.client.post(reverse('payments:create_withdrawal'), data={
            'amount': '60',
            'method': 'Telegram',
            'details': 'test_details'
        })
        wid = resp.json()['withdrawal_id']
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('90.00'))

        self.client.login(username='boss_admin', password='adminpassword')
        approve_url = reverse('admin:payments_withdrawal_approve', args=[wid])
        reject_url = reverse('admin:payments_withdrawal_reject', args=[wid])

        # First action: approve -> status=completed
        self.client.get(approve_url, follow=True)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('90.00'))

        # Second action attempt on same withdrawal: try to approve again
        self.client.get(approve_url, follow=True)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('90.00'))

        # Third action attempt on same withdrawal: try to reject after completed
        self.client.get(reject_url, follow=True)
        self.profile.refresh_from_db()
        # Balance must still be 90 (no refund for completed withdrawal)
        self.assertEqual(self.profile.balance, Decimal('90.00'))
        self.assertEqual(Transaction.objects.filter(reference_id=f'withdrawal_refund:{wid}').count(), 0)

    def test_09_deposit_system_remains_intact(self):
        """9. Существующая система пополнения депозитов НЕ затронута."""
        self.client.login(username='player_one', password='password123')
        resp = self.client.get(reverse('payments:deposit'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'ПОПОЛНЕНИЕ БАЛАНСА')

        dep_resp = self.client.post(reverse('payments:create_request'), data={'amount': '100'})
        self.assertEqual(dep_resp.status_code, 200)
        dep_data = dep_resp.json()
        self.assertTrue(dep_data['success'])

        tx = Transaction.objects.get(id=dep_data['transaction_id'])
        self.assertEqual(tx.status, 'pending')

        # Admin approves deposit
        self.client.login(username='boss_admin', password='adminpassword')
        self.client.get(reverse('admin:payments_tx_approve', args=[tx.id]), follow=True)

        tx.refresh_from_db()
        self.assertEqual(tx.status, 'completed')
        self.profile.refresh_from_db()
        # 150 + 100 = 250
        self.assertEqual(self.profile.balance, Decimal('250.00'))

    def test_10_admin_bulk_actions(self):
        """10. Массовые действия админа: approve_withdrawals_action и reject_withdrawals_action."""
        from payments.admin import approve_withdrawals_action, reject_withdrawals_action
        from django.contrib.admin.sites import site
        from payments.admin import WithdrawalAdmin

        # Create two withdrawals for player_one
        w1 = Withdrawal.objects.create(
            user=self.user,
            username=self.user.username,
            user_id_val=self.user.id,
            amount=Decimal('60.00'),
            method='Telegram',
            details='tg_1',
            status='pending'
        )
        w2 = Withdrawal.objects.create(
            user=self.user,
            username=self.user.username,
            user_id_val=self.user.id,
            amount=Decimal('70.00'),
            method='Telegram',
            details='tg_2',
            status='pending'
        )

        model_admin = WithdrawalAdmin(Withdrawal, site)

        # Mock request with admin user
        from django.test.client import RequestFactory
        factory = RequestFactory()
        req = factory.get('/')
        req.user = self.admin
        from django.contrib.messages.storage.fallback import FallbackStorage
        setattr(req, 'session', 'session')
        messages = FallbackStorage(req)
        setattr(req, '_messages', messages)

        # 1. Bulk approve w1 -> status becomes completed, balance untouched
        self.profile.balance = Decimal('100.00')
        self.profile.save()
        approve_withdrawals_action(model_admin, req, Withdrawal.objects.filter(id=w1.id))
        w1.refresh_from_db()
        self.assertEqual(w1.status, 'completed')
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('100.00'))

        # 2. Bulk reject w2 -> status becomes rejected, balance refunded (+70)
        reject_withdrawals_action(model_admin, req, Withdrawal.objects.filter(id=w2.id))
        w2.refresh_from_db()
        self.assertEqual(w2.status, 'rejected')
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('170.00'))


