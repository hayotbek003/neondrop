from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User

from cases.models import Category, Item, Case, CaseItem, Opening, PromoCode
from inventory.models import InventoryItem
from payments.models import Transaction
from users.models import Profile


class AdminDesignAndDashboardTests(TestCase):
    """
    Tests for the modern Cyberpunk Django Admin redesign:
    - Dashboard KPIs & Quick Buttons
    - Cases & CaseItemInline with item price, chance, rarity
    - Items management with rarity badge & containing cases
    - User management with inventory, openings, transactions inlines
    - Payments quick approve & withdrawal refund on reject
    """

    def setUp(self):
        # Clean existing migration-seeded cases/items to ensure clean isolation
        Case.objects.all().delete()
        Item.objects.all().delete()

        self.client = Client()
        self.admin_user = User.objects.create_superuser(
            username='AdminCyber',
            email='admin@neondrop.gg',
            password='AdminPassword123!'
        )
        self.admin_user.profile.balance = Decimal('1000.00')
        self.admin_user.profile.save()

        self.player = User.objects.create_user(
            username='GamerX',
            email='gamerx@neondrop.gg',
            password='PlayerPassword123!'
        )
        self.player.profile.balance = Decimal('350.00')
        self.player.profile.save()

        self.category = Category.objects.create(name='Оружие', slug='weapons')
        self.item = Item.objects.create(
            weapon_type='M4A4',
            skin_name='Howl',
            value=Decimal('500.00'),
            rarity='covert',
            rarity_color='#EB4B4B'
        )
        self.case = Case.objects.create(
            name='Contraband Case',
            slug='contraband-case',
            price=Decimal('100.00'),
            category=self.category,
            color_theme='demon-orange',
            active=True
        )
        self.case_item = CaseItem.objects.create(case=self.case, item=self.item, weight=50.0)

        self.opening = Opening.objects.create(
            user=self.player,
            case=self.case,
            item=self.item,
            price=Decimal('100.00'),
            server_seed='seed1',
            client_seed='client1',
            server_seed_hash='hash1',
            nonce=1
        )

        self.inv = InventoryItem.objects.create(
            user=self.player,
            item=self.item,
            opening=self.opening,
            is_sold=False,
            source='case'
        )

        self.tx_deposit = Transaction.objects.create(
            user=self.player,
            amount=Decimal('200.00'),
            balance_before=Decimal('150.00'),
            balance_after=Decimal('350.00'),
            transaction_type='deposit',
            status='pending',
            payment_method='telegram'
        )

        self.tx_withdraw = Transaction.objects.create(
            user=self.player,
            amount=Decimal('-100.00'),
            balance_before=Decimal('350.00'),
            balance_after=Decimal('250.00'),
            transaction_type='withdraw',
            status='pending',
            payment_method='crypto'
        )

        self.promo = PromoCode.objects.create(
            code='CYBERPROMO',
            bonus_value=Decimal('25.00'),
            blogger_name='CyberYT',
            blogger_percentage=Decimal('15.00'),
            starts_at='2026-01-01T00:00:00Z',
            expires_at='2026-12-31T23:59:59Z'
        )

    def test_dashboard_renders_with_kpis_and_quick_buttons(self):
        """Dashboard renders with all KPI metrics, quick buttons, and live drops."""
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode('utf-8')
        # Check branding and quick buttons
        self.assertIn('NEONDROP CYBER DASHBOARD', content)
        self.assertIn('CASES', content)
        self.assertIn('ITEMS', content)
        self.assertIn('USERS', content)
        self.assertIn('OPENINGS', content)
        self.assertIn('DEPOSITS', content)
        self.assertIn('WITHDRAWALS', content)
        self.assertIn('PROMO CODES', content)
        self.assertIn('BACKUP / RESTORE', content)

        # Check KPIs in context
        self.assertIn('kpi_total_users', response.context)
        self.assertEqual(response.context['kpi_total_users'], 2)
        self.assertEqual(response.context['kpi_cases_count'], 1)
        self.assertEqual(response.context['kpi_items_count'], 1)
        self.assertEqual(response.context['kpi_openings_count'], 1)
        self.assertEqual(response.context['kpi_pending_count'], 2)

    def test_case_admin_change_view_shows_case_item_details(self):
        """Case change form displays CaseItemInline with item price, chance %, and rarity."""
        self.client.force_login(self.admin_user)
        url = reverse('admin:cases_case_change', args=[self.case.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn('M4A4 | Howl', content)
        self.assertIn('500.00 UC', content)

    def test_item_admin_list_view(self):
        """Item list view shows price, rarity badge, and related cases."""
        self.client.force_login(self.admin_user)
        url = reverse('admin:cases_item_changelist')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn('M4A4 | Howl', content)
        self.assertIn('500.00 UC', content)
        self.assertIn('Contraband Case', content)

    def test_user_admin_change_view_inlines(self):
        """User change form shows inlines for profile, inventory, openings, transactions."""
        self.client.force_login(self.admin_user)
        url = reverse('admin:auth_user_change', args=[self.player.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn('GamerX', content)
        self.assertIn('350.00', content)
        self.assertIn('M4A4 | Howl', content)

    def test_transaction_quick_approve_deposit(self):
        """Quick approve on pending deposit credits user balance and marks completed."""
        self.client.force_login(self.admin_user)
        initial_balance = self.player.profile.balance
        url = reverse('admin:payments_tx_approve', args=[self.tx_deposit.id])
        response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 200)

        self.tx_deposit.refresh_from_db()
        self.assertEqual(self.tx_deposit.status, 'completed')
        self.player.profile.refresh_from_db()
        self.assertEqual(self.player.profile.balance, initial_balance + Decimal('200.00'))

    def test_transaction_quick_reject_withdrawal_refunds_funds(self):
        """Quick reject on pending withdrawal refunds the debited funds back to the user."""
        self.client.force_login(self.admin_user)
        initial_balance = self.player.profile.balance
        url = reverse('admin:payments_tx_reject', args=[self.tx_withdraw.id])
        response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 200)

        self.tx_withdraw.refresh_from_db()
        self.assertEqual(self.tx_withdraw.status, 'rejected')
        self.player.profile.refresh_from_db()
        # 100.00 refunded back
        self.assertEqual(self.player.profile.balance, initial_balance + Decimal('100.00'))
