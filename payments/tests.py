import urllib.parse
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse

from payments.models import Transaction, Withdrawal
from users.models import Profile, AdminPermissionProfile


class WithdrawalSystemTestCase(TestCase):
    """
    Comprehensive test suite covering all requirements of the NEONDROP withdrawal system:
    1. Authorized user sees "Вывести" button in UI.
    2. Unauthorized user does NOT see "Вывести" button in UI.
    3. Creation of withdrawal request creates pending Withdrawal record.
    4. Balance is NOT deducted upon creation of withdrawal request.
    5. Telegram URL contains username, user ID, email, amount, withdrawal ID and is properly url-encoded.
    6. Amount validation (minimum 60 UC, cannot exceed user balance).
    7. Admin can approve withdrawal request.
    8. Upon admin approval, balance is deducted exactly once and Transaction record is created.
    9. Repeated approval is blocked.
    10. Rejected withdrawal request does NOT deduct user balance.
    11. Insufficient balance prevents approval of withdrawal.
    """

    def setUp(self):
        self.client = Client()

        # Create regular user
        self.user = User.objects.create_user(
            username='player_one',
            password='password123',
            email='player_one@neondrop.gg'
        )
        # Profile is created or updated
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
        """1. Авторизованный пользователь видит кнопку «Вывести»."""
        self.client.login(username='player_one', password='password123')
        resp = self.client.get(reverse('cases:home'))
        self.assertEqual(resp.status_code, 200)
        # Button / modal trigger must be present in HTML
        self.assertContains(resp, 'Вывести')
        self.assertContains(resp, 'open-withdraw-modal-trigger')
        self.assertContains(resp, 'withdrawalModal')

    def test_02_unauthorized_user_does_not_see_withdraw_button(self):
        """2. Неавторизованный пользователь НЕ видит кнопку «Вывести»."""
        self.client.logout()
        resp = self.client.get(reverse('cases:home'))
        self.assertEqual(resp.status_code, 200)
        # Should not contain withdrawal button or modal for anonymous guest
        self.assertNotContains(resp, 'open-withdraw-modal-trigger')
        self.assertNotContains(resp, 'withdrawalModal')

    def test_03_create_withdrawal_request_pending_status(self):
        """3. Создание заявки со статусом pending."""
        self.client.login(username='player_one', password='password123')
        payload = {
            'amount': '75.00',
            'method': 'PUBG Mobile (Player ID)',
            'details': 'ID: 5123456789, Nick: NeonSniper'
        }
        resp = self.client.post(reverse('payments:create_withdrawal'), data=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertIn('withdrawal_id', data)

        w = Withdrawal.objects.get(id=data['withdrawal_id'])
        self.assertEqual(w.user, self.user)
        self.assertEqual(w.username, 'player_one')
        self.assertEqual(w.user_id_val, self.user.id)
        self.assertEqual(w.amount, Decimal('75.00'))
        self.assertEqual(w.method, 'PUBG Mobile (Player ID)')
        self.assertEqual(w.details, 'ID: 5123456789, Nick: NeonSniper')
        self.assertEqual(w.status, 'pending')

    def test_04_balance_not_deducted_on_creation(self):
        """4. Баланс НЕ списывается при создании заявки."""
        self.client.login(username='player_one', password='password123')
        initial_balance = Decimal('150.00')
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, initial_balance)

        payload = {
            'amount': '60.00',
            'method': 'Банковская карта (UZS: Uzcard / Humo)',
            'details': '8600 0000 1111 2222'
        }
        resp = self.client.post(reverse('payments:create_withdrawal'), data=payload)
        self.assertEqual(resp.status_code, 200)

        self.profile.refresh_from_db()
        # Balance must remain completely unchanged!
        self.assertEqual(self.profile.balance, initial_balance)
        self.assertEqual(Transaction.objects.filter(user=self.user, transaction_type='withdraw').count(), 0)

    def test_05_telegram_url_contains_username_userid_and_encoded_msg(self):
        """5. Telegram URL содержит username, user ID и правильный URL encoding."""
        self.client.login(username='player_one', password='password123')
        payload = {
            'amount': '65.00',
            'method': 'USDT TRC20',
            'details': 'TX9xyz123456789trc20address'
        }
        resp = self.client.post(reverse('payments:create_withdrawal'), data=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        tg_url = data['telegram_url']

        self.assertTrue(tg_url.startswith('https://t.me/neondrop_admin?text='))
        # Parse query params
        parsed = urllib.parse.urlparse(tg_url)
        params = urllib.parse.parse_qs(parsed.query)
        self.assertIn('text', params)
        decoded_text = params['text'][0]

        # Verify exact required fields inside pre-filled Telegram message
        self.assertIn('ЗАЯВКА НА ВЫВОД NEONDROP', decoded_text)
        self.assertIn(f'Пользователь: {self.user.username}', decoded_text)
        self.assertIn(f'ID: {self.user.id}', decoded_text)
        self.assertIn('Email: player_one@neondrop.gg', decoded_text)
        self.assertIn('Сумма: 65 UC', decoded_text)
        self.assertIn('Способ получения: USDT TRC20', decoded_text)
        self.assertIn('Реквизиты: TX9xyz123456789trc20address', decoded_text)
        self.assertIn(f'Заявка №: {data["withdrawal_id"]}', decoded_text)
        self.assertIn('Просьба проверить заявку и подтвердить вывод.', decoded_text)

    def test_06_amount_validation(self):
        """6. Валидация суммы: минимум 60 UC и не больше баланса."""
        self.client.login(username='player_one', password='password123')

        # Test less than 60 UC
        resp_too_small = self.client.post(reverse('payments:create_withdrawal'), data={
            'amount': '59.99',
            'method': 'Card',
            'details': 'Card details'
        })
        self.assertEqual(resp_too_small.status_code, 400)
        self.assertFalse(resp_too_small.json()['success'])
        self.assertIn('Минимальная сумма', resp_too_small.json()['error'])

        # Test more than user balance (150 UC)
        resp_too_large = self.client.post(reverse('payments:create_withdrawal'), data={
            'amount': '150.01',
            'method': 'Card',
            'details': 'Card details'
        })
        self.assertEqual(resp_too_large.status_code, 400)
        self.assertFalse(resp_too_large.json()['success'])
        self.assertIn('Недостаточно средств', resp_too_large.json()['error'])

    def test_07_admin_can_approve_and_balance_deducted_once(self):
        """7 & 8. Админ может одобрить; при одобрении баланс списывается один раз; создаётся Transaction."""
        # 1. Create withdrawal request
        w = Withdrawal.objects.create(
            user=self.user,
            username=self.user.username,
            user_id_val=self.user.id,
            amount=Decimal('40.00'),
            method='Card',
            details='1111 2222 3333 4444',
            status='pending'
        )

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('150.00'))

        # 2. Login as admin and approve
        self.client.login(username='boss_admin', password='adminpassword')
        approve_url = reverse('admin:payments_withdrawal_approve', args=[w.id])
        resp = self.client.get(approve_url, follow=True)
        self.assertEqual(resp.status_code, 200)

        # 3. Check withdrawal status
        w.refresh_from_db()
        self.assertEqual(w.status, 'approved')
        self.assertEqual(w.processed_by, self.admin)
        self.assertIsNotNone(w.related_transaction)

        # 4. Check user balance: 150 - 40 = 110
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('110.00'))

        # 5. Check transaction ledger entry
        tx = w.related_transaction
        self.assertEqual(tx.user, self.user)
        self.assertEqual(tx.amount, Decimal('-40.00'))
        self.assertEqual(tx.balance_before, Decimal('150.00'))
        self.assertEqual(tx.balance_after, Decimal('110.00'))
        self.assertEqual(tx.transaction_type, 'withdraw')
        self.assertEqual(tx.status, 'completed')

    def test_09_repeated_approval_impossible(self):
        """9. Повторное одобрение невозможно."""
        w = Withdrawal.objects.create(
            user=self.user,
            username=self.user.username,
            user_id_val=self.user.id,
            amount=Decimal('30.00'),
            method='Card',
            details='1111 2222',
            status='pending'
        )

        self.client.login(username='boss_admin', password='adminpassword')
        approve_url = reverse('admin:payments_withdrawal_approve', args=[w.id])

        # First approval
        self.client.get(approve_url, follow=True)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('120.00'))

        # Second approval attempt on already approved request
        resp_repeat = self.client.get(approve_url, follow=True)
        self.assertEqual(resp_repeat.status_code, 200)

        # Balance must still be 120 (NOT deducted again)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('120.00'))
        self.assertEqual(Transaction.objects.filter(reference_id=f'withdrawal:{w.id}').count(), 1)

    def test_10_rejected_withdrawal_does_not_deduct_balance(self):
        """10. Отклонённая заявка не списывает баланс."""
        w = Withdrawal.objects.create(
            user=self.user,
            username=self.user.username,
            user_id_val=self.user.id,
            amount=Decimal('60.00'),
            method='Card',
            details='Invalid account',
            status='pending'
        )

        self.client.login(username='boss_admin', password='adminpassword')
        reject_url = reverse('admin:payments_withdrawal_reject', args=[w.id])
        resp = self.client.get(reject_url, follow=True)
        self.assertEqual(resp.status_code, 200)

        w.refresh_from_db()
        self.assertEqual(w.status, 'rejected')
        self.assertEqual(w.processed_by, self.admin)

        # Balance must remain 150.00
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('150.00'))
        self.assertEqual(Transaction.objects.filter(reference_id=f'withdrawal:{w.id}').count(), 0)

    def test_11_insufficient_balance_prevents_approval(self):
        """11. Недостаточный баланс в момент одобрения не позволяет списать и отклоняет операцию."""
        w = Withdrawal.objects.create(
            user=self.user,
            username=self.user.username,
            user_id_val=self.user.id,
            amount=Decimal('100.00'),
            method='Card',
            details='1111',
            status='pending'
        )

        # Simulate user spent money on cases before admin approved
        self.profile.balance = Decimal('20.00')
        self.profile.save()

        self.client.login(username='boss_admin', password='adminpassword')
        approve_url = reverse('admin:payments_withdrawal_approve', args=[w.id])
        resp = self.client.get(approve_url, follow=True)
        self.assertEqual(resp.status_code, 200)

        # Request must remain pending or not approved, balance must NOT go negative
        w.refresh_from_db()
        self.assertNotEqual(w.status, 'approved')
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('20.00'))

    def test_12_deposit_system_not_broken(self):
        """12. Проверка, что существующая система пополнения депозитов не сломана."""
        self.client.login(username='player_one', password='password123')
        resp = self.client.get(reverse('payments:deposit'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'ПОПОЛНЕНИЕ БАЛАНСА')

        # Test deposit request creation
        dep_resp = self.client.post(reverse('payments:create_request'), data={'amount': '100'})
        self.assertEqual(dep_resp.status_code, 200)
        dep_data = dep_resp.json()
        self.assertTrue(dep_data['success'])
        self.assertIn('transaction_id', dep_data)

        # Admin approves deposit
        tx = Transaction.objects.get(id=dep_data['transaction_id'])
        self.assertEqual(tx.status, 'pending')
        self.assertEqual(tx.transaction_type, 'deposit')

        self.client.login(username='boss_admin', password='adminpassword')
        approve_dep_url = reverse('admin:payments_tx_approve', args=[tx.id])
        self.client.get(approve_dep_url, follow=True)

        tx.refresh_from_db()
        self.assertEqual(tx.status, 'completed')
        self.profile.refresh_from_db()
        # 150 + 100 = 250
        self.assertEqual(self.profile.balance, Decimal('250.00'))

