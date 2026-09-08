import logging
from datetime import timedelta
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from users.models import Profile, AdminPermissionProfile, has_admin_perm, ADMIN_PERMISSIONS_LIST
from cases.models import Case, Item, CaseItem, PromoCode, PromoCodeUse, Opening
from payments.models import Transaction


class AdminManagementAndBonusTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Superuser (Root Administrator)
        self.superuser = User.objects.create_superuser(
            username='RootAdmin',
            email='root@neondrop.gg',
            password='password123'
        )
        self.superuser.profile.balance = Decimal('500.00')
        self.superuser.profile.save()

        # Regular Staff member without permissions
        self.staff_user = User.objects.create_user(
            username='ModeratorLeo',
            email='leo@neondrop.gg',
            password='password123',
            is_staff=True
        )
        self.staff_user.profile.balance = Decimal('100.00')
        self.staff_user.profile.save()

        # Ordinary Player
        self.player = User.objects.create_user(
            username='PlayerOne',
            email='player1@neondrop.gg',
            password='password123'
        )
        self.player.profile.balance = Decimal('50.00')
        self.player.profile.save()

        now = timezone.now()
        # Promo Code
        self.blogger_promo = PromoCode.objects.create(
            code='BLOGGER10',
            blogger_name='ProGamer',
            blogger_percentage=Decimal('10.00'),
            bonus_type='percentage',
            bonus_value=Decimal('10.00'),
            starts_at=now - timedelta(days=1),
            expires_at=now + timedelta(days=30),
            is_active=True
        )

        self.alt_promo = PromoCode.objects.create(
            code='STREAMER20',
            blogger_name='TopStreamer',
            blogger_percentage=Decimal('20.00'),
            bonus_type='percentage',
            bonus_value=Decimal('20.00'),
            starts_at=now - timedelta(days=1),
            expires_at=now + timedelta(days=30),
            is_active=True
        )

        # Create case & item
        self.case = Case.objects.create(
            name='Cyber Neon Case',
            slug='cyber-neon-case',
            price=Decimal('20.00')
        )
        self.item = Item.objects.create(
            name='AK-47 | Neon Revolution',
            weapon_type='AK-47',
            skin_name='Neon Revolution',
            value=Decimal('50.00'),
            rarity='covert'
        )
        self.case_item = CaseItem.objects.create(
            case=self.case,
            item=self.item,
            weight=100
        )

    # =========================================================================
    # 1. REGISTRATION BONUS TESTS (5.00 UC)
    # =========================================================================

    def test_new_user_registration_gets_exactly_5_uc(self):
        """Newly registered user must receive exactly 5.00 UC welcome bonus (not 100 UC)."""
        response = self.client.post(reverse('users:register'), {
            'username': 'BonusTester',
            'email': 'bonustester@gmail.com',
            'password': 'ComplexPassword123!',
            'password_confirm': 'ComplexPassword123!',
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        new_user = User.objects.get(username='BonusTester')
        new_user.profile.refresh_from_db()

        # Balance must be exactly 5.00 UC
        self.assertEqual(new_user.profile.balance, Decimal('5.00'))

        # Check welcome flash message
        messages = list(response.context['messages'])
        self.assertTrue(any("5.00 UC" in str(m) for m in messages))
        self.assertFalse(any("100.00" in str(m) for m in messages))

    def test_google_oauth_user_creation_gets_exactly_5_uc(self):
        """A user created via Google OAuth must also start with exactly 5.00 UC."""
        from users.oauth import get_or_create_google_user
        google_info = {
            'sub': 'google-uid-test-5uc',
            'email': 'googleplayer@gmail.com',
            'name': 'Google Player',
            'picture': 'https://lh3.googleusercontent.com/photo.jpg'
        }
        user, created = get_or_create_google_user(google_info)
        self.assertTrue(created)
        self.assertEqual(user.profile.balance, Decimal('5.00'))

    def test_existing_user_balance_is_not_modified_or_recredited(self):
        """Existing user balance must remain unchanged when logging in or interacting."""
        initial_balance = self.player.profile.balance  # 50.00 UC
        self.client.login(username='PlayerOne', password='password123')
        resp = self.client.get(reverse('cases:home'))
        self.assertEqual(resp.status_code, 200)

        self.player.profile.refresh_from_db()
        self.assertEqual(self.player.profile.balance, initial_balance)

    # =========================================================================
    # 2. PROMO CODE AT MANUAL DEPOSIT (ADMIN)
    # =========================================================================

    def test_manual_deposit_links_user_to_promo_code(self):
        """
        When confirming a deposit in Django admin with a promo_code,
        the user must be linked to PromoCodeUse and deposit itself gives 0 UC commission.
        """
        self.client.login(username='RootAdmin', password='password123')

        tx = Transaction.objects.create(
            user=self.player,
            amount=Decimal('100.00'),
            transaction_type='deposit',
            status='pending',
            promo_code=self.blogger_promo
        )

        initial_balance = self.player.profile.balance  # 50.00

        # Approve deposit
        approve_url = reverse('admin:payments_tx_approve', args=[tx.id])
        resp = self.client.get(approve_url, follow=True)
        self.assertEqual(resp.status_code, 200)

        # Check balance
        self.player.profile.refresh_from_db()
        self.assertEqual(self.player.profile.balance, initial_balance + Decimal('100.00'))

        # Check PromoCodeUse was created
        link = PromoCodeUse.objects.filter(user=self.player, promo_code=self.blogger_promo).first()
        self.assertIsNotNone(link)

        # Commission on deposit itself is 0 UC (only net loss counts)
        stats = self.blogger_promo.get_stats_all_time()
        self.assertEqual(stats['total_deposits'], Decimal('100.00'))
        self.assertEqual(stats['blogger_payout'], Decimal('0.00'))

    def test_promo_code_rebind_allowed_for_superuser_with_audit_log(self):
        """
        When superuser deposits with a DIFFERENT promo code for an already linked user,
        re-binding is permitted and logged.
        """
        # First link to blogger_promo
        PromoCodeUse.objects.create(user=self.player, promo_code=self.blogger_promo)

        self.client.login(username='RootAdmin', password='password123')

        tx = Transaction.objects.create(
            user=self.player,
            amount=Decimal('50.00'),
            transaction_type='deposit',
            status='pending',
            promo_code=self.alt_promo
        )

        with self.assertLogs('neondrop.audit', level='INFO') as cm:
            approve_url = reverse('admin:payments_tx_approve', args=[tx.id])
            self.client.get(approve_url, follow=True)

        # Check audit log contains PROMO_CODE_REBIND
        self.assertTrue(any('PROMO_CODE_REBIND' in msg for msg in cm.output))

        # Latest link is now alt_promo
        latest_link = PromoCodeUse.objects.filter(user=self.player).order_by('-used_at').first()
        self.assertEqual(latest_link.promo_code, self.alt_promo)

    def test_promo_code_rebind_denied_for_regular_staff(self):
        """
        When a non-superuser staff member processes a deposit with a different promo code,
        re-binding is denied, keeping the original promo code link.
        """
        # Link user to original promo
        PromoCodeUse.objects.create(user=self.player, promo_code=self.blogger_promo)

        # Give staff user permission to approve deposits
        AdminPermissionProfile.objects.create(
            user=self.staff_user,
            can_view_deposits=True,
            can_approve_deposits=True
        )

        self.client.login(username='ModeratorLeo', password='password123')

        tx = Transaction.objects.create(
            user=self.player,
            amount=Decimal('50.00'),
            transaction_type='deposit',
            status='pending',
            promo_code=self.alt_promo
        )

        with self.assertLogs('neondrop.security', level='WARNING') as cm:
            approve_url = reverse('admin:payments_tx_approve', args=[tx.id])
            self.client.get(approve_url, follow=True)

        self.assertTrue(any('PROMO_CODE_REBIND_DENIED' in msg for msg in cm.output))

        # Link to alt_promo was NOT created
        self.assertFalse(PromoCodeUse.objects.filter(user=self.player, promo_code=self.alt_promo).exists())

    # =========================================================================
    # 3. ADMIN MANAGEMENT SYSTEM («👑 Управление администраторами»)
    # =========================================================================

    def test_admin_management_page_accessible_only_to_superuser(self):
        """Only is_superuser=True can access /admin/administrators/. Staff gets 403."""
        # Player gets redirected to login
        self.client.login(username='PlayerOne', password='password123')
        resp = self.client.get(reverse('admin_administrators'))
        self.assertEqual(resp.status_code, 403)

        # Staff user gets 403 Forbidden
        self.client.login(username='ModeratorLeo', password='password123')
        resp = self.client.get(reverse('admin_administrators'))
        self.assertEqual(resp.status_code, 403)

        # Superuser gets 200 OK
        self.client.login(username='RootAdmin', password='password123')
        resp = self.client.get(reverse('admin_administrators'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '👑')
        self.assertContains(resp, 'УПРАВЛЕНИЕ АДМИНИСТРАТОРАМИ')

    def test_superuser_can_appoint_administrator_with_granular_permissions(self):
        """Superuser appoints a player as Administrator with specific checkboxes."""
        self.client.login(username='RootAdmin', password='password123')

        appoint_url = reverse('admin_assign_administrator')
        post_data = {
            'user_id': self.player.id,
            'perm_can_view_cases': '1',
            'perm_can_edit_cases': '1',
            'perm_can_view_deposits': '1',
            'perm_can_approve_deposits': '1',
        }

        resp = self.client.post(appoint_url, post_data, follow=True)
        self.assertEqual(resp.status_code, 200)

        # Player is now staff
        self.player.refresh_from_db()
        self.assertTrue(self.player.is_staff)
        self.assertFalse(self.player.is_superuser)

        # Check permissions
        self.assertTrue(has_admin_perm(self.player, 'can_view_cases'))
        self.assertTrue(has_admin_perm(self.player, 'can_edit_cases'))
        self.assertTrue(has_admin_perm(self.player, 'can_view_deposits'))
        self.assertTrue(has_admin_perm(self.player, 'can_approve_deposits'))
        self.assertFalse(has_admin_perm(self.player, 'can_restore_backup'))
        self.assertFalse(has_admin_perm(self.player, 'can_edit_blogger_percent'))

    def test_superuser_can_update_permissions_and_toggle_status(self):
        """Superuser can update permissions and block/unblock administrators."""
        self.client.login(username='RootAdmin', password='password123')

        # Update perms
        update_url = reverse('admin_update_perms', args=[self.staff_user.id])
        resp = self.client.post(update_url, {
            'perm_can_view_blogger_stats': '1',
            'perm_can_view_backup': '1',
        }, follow=True)
        self.assertEqual(resp.status_code, 200)

        self.assertTrue(has_admin_perm(self.staff_user, 'can_view_blogger_stats'))
        self.assertTrue(has_admin_perm(self.staff_user, 'can_view_backup'))
        self.assertFalse(has_admin_perm(self.staff_user, 'can_create_backup'))

        # Toggle status to block
        toggle_url = reverse('admin_toggle_status', args=[self.staff_user.id])
        resp = self.client.post(toggle_url, follow=True)
        self.assertEqual(resp.status_code, 200)

        self.staff_user.refresh_from_db()
        self.assertFalse(self.staff_user.is_active)

        # Blocked staff has no admin permissions
        self.assertFalse(has_admin_perm(self.staff_user, 'can_view_backup'))

        # Toggle status to unblock
        resp = self.client.post(toggle_url, follow=True)
        self.staff_user.refresh_from_db()
        self.assertTrue(self.staff_user.is_active)

    def test_revoke_administrator(self):
        """Superuser can revoke administrator privileges (is_staff=False)."""
        self.client.login(username='RootAdmin', password='password123')

        revoke_url = reverse('admin_revoke_administrator', args=[self.staff_user.id])
        resp = self.client.post(revoke_url, follow=True)
        self.assertEqual(resp.status_code, 200)

        self.staff_user.refresh_from_db()
        self.assertFalse(self.staff_user.is_staff)

    def test_self_deactivation_and_self_revocation_are_blocked(self):
        """Superuser cannot accidentally block or revoke themselves."""
        self.client.login(username='RootAdmin', password='password123')

        # Try toggle self
        resp = self.client.post(reverse('admin_toggle_status', args=[self.superuser.id]), follow=True)
        self.superuser.refresh_from_db()
        self.assertTrue(self.superuser.is_active)

        # Try revoke self
        resp = self.client.post(reverse('admin_revoke_administrator', args=[self.superuser.id]), follow=True)
        self.superuser.refresh_from_db()
        self.assertTrue(self.superuser.is_staff)
        self.assertTrue(self.superuser.is_superuser)

    # =========================================================================
    # 4. BACKEND PERMISSION ENFORCEMENT
    # =========================================================================

    def test_blogger_dashboard_permission_enforcement(self):
        """Blogger dashboard requires can_view_blogger_stats permission."""
        self.client.login(username='ModeratorLeo', password='password123')

        # Without permission -> 403
        resp = self.client.get(reverse('admin_blogger_dashboard'))
        self.assertEqual(resp.status_code, 403)

        # Grant permission
        AdminPermissionProfile.objects.create(
            user=self.staff_user,
            can_view_blogger_stats=True
        )

        resp = self.client.get(reverse('admin_blogger_dashboard'))
        self.assertEqual(resp.status_code, 200)

    def test_backup_restore_permission_enforcement(self):
        """Backup/Restore views strictly enforce can_view_backup, can_create_backup, can_restore_backup."""
        self.client.login(username='ModeratorLeo', password='password123')

        # View backup page -> 403
        resp = self.client.get(reverse('admin_backup_restore'))
        self.assertEqual(resp.status_code, 403)

        # Download backup -> 403
        resp = self.client.get(reverse('admin_backup_download'))
        self.assertEqual(resp.status_code, 403)

        # Grant only can_view_backup
        profile = AdminPermissionProfile.objects.create(
            user=self.staff_user,
            can_view_backup=True
        )

        resp = self.client.get(reverse('admin_backup_restore'))
        self.assertEqual(resp.status_code, 200)

        # Download still forbidden without can_create_backup
        resp = self.client.get(reverse('admin_backup_download'))
        self.assertEqual(resp.status_code, 403)

        # Grant can_create_backup
        profile.can_create_backup = True
        profile.save()

        resp = self.client.get(reverse('admin_backup_download'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['content-type'], 'application/zip')

    def test_deposit_approval_permission_enforcement(self):
        """Staff without can_approve_deposits cannot approve deposits."""
        self.client.login(username='ModeratorLeo', password='password123')

        tx = Transaction.objects.create(
            user=self.player,
            amount=Decimal('50.00'),
            transaction_type='deposit',
            status='pending'
        )

        resp = self.client.get(reverse('admin:payments_tx_approve', args=[tx.id]), follow=True)
        tx.refresh_from_db()
        self.assertEqual(tx.status, 'pending')  # Still pending!

        # Grant permission
        AdminPermissionProfile.objects.create(
            user=self.staff_user,
            can_approve_deposits=True
        )

        resp = self.client.get(reverse('admin:payments_tx_approve', args=[tx.id]), follow=True)
        tx.refresh_from_db()
        self.assertEqual(tx.status, 'completed')  # Successfully approved!
