from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from users.models import GoogleAccount, Profile
from users.oauth import GoogleOAuthError


class GoogleAuthAndRegistrationTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_standard_registration_and_login_no_multiple_backends_error(self):
        """
        Verify that registering a new user does NOT trigger:
        ValueError: You have multiple authentication backends configured...
        and correctly logs the user in with welcome balance.
        """
        register_url = reverse('users:register')
        payload = {
            'username': 'NeonProwler',
            'email': 'prowler@neondrop.gg',
            'telegram_username': '@prowler',
            'password': 'SecurePassword123!',
            'password_confirm': 'SecurePassword123!',
        }

        response = self.client.post(register_url, payload, follow=True)
        self.assertEqual(response.status_code, 200)

        # User must exist in DB
        user = User.objects.filter(username='NeonProwler').first()
        self.assertIsNotNone(user)
        self.assertEqual(user.email, 'prowler@neondrop.gg')
        self.assertTrue(user.check_password('SecurePassword123!'))

        # User must be authenticated in session
        self.assertEqual(int(self.client.session.get('_auth_user_id')), user.id)

        # Welcome balance must be credited
        self.assertEqual(user.profile.balance, Decimal('5.00'))
        self.assertEqual(user.profile.telegram_username, '@prowler')

    def test_standard_username_and_email_login(self):
        """
        Verify that standard login works with username AND email (case-insensitive).
        """
        user = User.objects.create_user(
            username='GamerAlpha',
            email='alpha.gamer@neondrop.gg',
            password='GamerPassword123!'
        )

        login_url = reverse('users:login')

        # 1. Login with username
        resp1 = self.client.post(login_url, {
            'username_or_email': 'gameralpha',  # lowercase test
            'password': 'GamerPassword123!'
        }, follow=True)
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(int(self.client.session.get('_auth_user_id')), user.id)

        # Logout
        self.client.logout()
        self.assertNotIn('_auth_user_id', self.client.session)

        # 2. Login with email (mixed case)
        resp2 = self.client.post(login_url, {
            'username_or_email': 'ALPHA.GAMER@NEONDROP.GG',
            'password': 'GamerPassword123!'
        }, follow=True)
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(int(self.client.session.get('_auth_user_id')), user.id)

    @patch('users.views.get_google_client_id', return_value='')
    def test_google_login_redirect_when_not_configured(self, mock_client_id):
        """
        When Google OAuth credentials are not set, redirect to login with a warning.
        """
        url = reverse('users:google_login')
        response = self.client.get(url)
        self.assertRedirects(response, reverse('users:login'))

    @patch('users.views.get_google_client_id', return_value='test-client-id-12345')
    @patch('users.views.get_google_client_secret', return_value='test-client-secret-abcde')
    def test_google_login_initiates_oauth_with_state(self, mock_secret, mock_id):
        """
        When credentials are set, google_login_view redirects to accounts.google.com
        with client_id, scope, state, and redirect_uri.
        """
        url = reverse('users:google_login')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)
        redirect_url = response.url
        self.assertTrue(redirect_url.startswith('https://accounts.google.com/o/oauth2/v2/auth'))
        self.assertIn('client_id=test-client-id-12345', redirect_url)
        self.assertIn('response_type=code', redirect_url)
        self.assertIn('state=', redirect_url)

        # State must be saved in session
        state = self.client.session.get('google_oauth_state')
        self.assertIsNotNone(state)
        self.assertIn(state, redirect_url)

    def test_google_callback_user_cancellation(self):
        """
        When user cancels Google prompt (error=access_denied), handle gracefully.
        """
        url = reverse('users:google_callback') + '?error=access_denied'
        response = self.client.get(url, follow=True)
        self.assertRedirects(response, reverse('users:login'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_google_callback_invalid_csrf_state(self):
        """
        When state does not match session, reject callback (CSRF prevention).
        """
        # Set session state
        session = self.client.session
        session['google_oauth_state'] = 'correct_state_secret_123'
        session.save()

        url = reverse('users:google_callback') + '?code=valid_code&state=attacker_state_tampered'
        response = self.client.get(url, follow=True)
        self.assertRedirects(response, reverse('users:login'))
        self.assertNotIn('_auth_user_id', self.client.session)

    @patch('users.views.fetch_google_user_info')
    @patch('users.views.exchange_code_for_tokens')
    def test_google_callback_registers_new_user(self, mock_exchange, mock_userinfo):
        """
        First-time Google login:
        - Creates User with unusable password
        - Derives username and profile
        - Sets welcome balance
        - Links GoogleAccount
        - Authenticates user session
        """
        mock_exchange.return_value = {'access_token': 'fake-token-123'}
        mock_userinfo.return_value = {
            'sub': 'google-uid-1001',
            'email': 'newplayer@gmail.com',
            'name': 'Alex Mercer',
            'picture': 'https://lh3.googleusercontent.com/avatar.jpg'
        }

        # Set valid state in session
        session = self.client.session
        session['google_oauth_state'] = 'secure_state_val_456'
        session.save()

        url = reverse('users:google_callback') + '?code=valid_auth_code&state=secure_state_val_456'
        response = self.client.get(url, follow=True)

        self.assertRedirects(response, reverse('cases:home'))

        # Check user creation
        user = User.objects.filter(email='newplayer@gmail.com').first()
        self.assertIsNotNone(user)
        self.assertIn('Alex_Mercer', user.username)
        # Google password must NEVER be set or usable
        self.assertFalse(user.has_usable_password())

        # Check GoogleAccount link
        g_acc = GoogleAccount.objects.filter(user=user).first()
        self.assertIsNotNone(g_acc)
        self.assertEqual(g_acc.google_id, 'google-uid-1001')
        self.assertEqual(g_acc.email, 'newplayer@gmail.com')

        # Check profile balance
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.balance, Decimal('5.00'))
        self.assertEqual(user.profile.avatar_url, 'https://lh3.googleusercontent.com/avatar.jpg')

        # Check session
        self.assertEqual(int(self.client.session.get('_auth_user_id')), user.id)

    @patch('users.views.fetch_google_user_info')
    @patch('users.views.exchange_code_for_tokens')
    def test_google_callback_links_existing_user_case_insensitive(self, mock_exchange, mock_userinfo):
        """
        Existing user with same email (regardless of case):
        - Links GoogleAccount to existing user
        - Does NOT create duplicate user
        - Preserves existing password and balance
        - Successfully authenticates user session
        """
        existing_user = User.objects.create_user(
            username='ExistingSniper',
            email='sniper.pro@gmail.com',
            password='OriginalPassword999!'
        )
        existing_user.profile.balance = Decimal('777.50')
        existing_user.profile.save()

        mock_exchange.return_value = {'access_token': 'fake-token-456'}
        # Google returns email in uppercase/mixed case
        mock_userinfo.return_value = {
            'sub': 'google-uid-2002',
            'email': 'SNIPER.PRO@GMAIL.COM',
            'name': 'Sniper Pro',
            'picture': 'https://lh3.googleusercontent.com/sniper.jpg'
        }

        session = self.client.session
        session['google_oauth_state'] = 'state_link_test_789'
        session.save()

        url = reverse('users:google_callback') + '?code=valid_code_2&state=state_link_test_789'
        response = self.client.get(url, follow=True)

        self.assertRedirects(response, reverse('cases:home'))

        # Only 1 user must exist with this email
        self.assertEqual(User.objects.filter(email__iexact='sniper.pro@gmail.com').count(), 1)

        # Existing user's password must remain intact
        existing_user.refresh_from_db()
        self.assertTrue(existing_user.check_password('OriginalPassword999!'))
        self.assertEqual(existing_user.profile.balance, Decimal('777.50'))

        # GoogleAccount is linked
        self.assertEqual(existing_user.google_account.google_id, 'google-uid-2002')

        # Authenticated as existing user
        self.assertEqual(int(self.client.session.get('_auth_user_id')), existing_user.id)

    @patch('users.views.fetch_google_user_info')
    @patch('users.views.exchange_code_for_tokens')
    def test_repeated_google_login(self, mock_exchange, mock_userinfo):
        """
        Subsequent logins with already-linked GoogleAccount log in immediately.
        """
        user = User.objects.create_user(
            username='RepeatedTester',
            email='repeat@gmail.com'
        )
        GoogleAccount.objects.create(user=user, google_id='google-uid-3003', email='repeat@gmail.com')

        mock_exchange.return_value = {'access_token': 'fake-token-789'}
        mock_userinfo.return_value = {
            'sub': 'google-uid-3003',
            'email': 'repeat@gmail.com',
            'name': 'Repeated Tester'
        }

        session = self.client.session
        session['google_oauth_state'] = 'repeat_state_123'
        session.save()

        url = reverse('users:google_callback') + '?code=code_3&state=repeat_state_123'
        response = self.client.get(url, follow=True)

        self.assertRedirects(response, reverse('cases:home'))
        self.assertEqual(int(self.client.session.get('_auth_user_id')), user.id)

    @patch('users.views.exchange_code_for_tokens')
    def test_google_callback_oauth_error(self, mock_exchange):
        """
        When token exchange raises GoogleOAuthError, redirect to login with error message.
        """
        mock_exchange.side_effect = GoogleOAuthError("Token exchange expired")

        session = self.client.session
        session['google_oauth_state'] = 'error_state_123'
        session.save()

        url = reverse('users:google_callback') + '?code=bad_code&state=error_state_123'
        response = self.client.get(url, follow=True)

        self.assertRedirects(response, reverse('users:login'))
        self.assertNotIn('_auth_user_id', self.client.session)
