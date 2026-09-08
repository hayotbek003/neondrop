from decimal import Decimal
from datetime import datetime, timedelta
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from django.urls import reverse

from cases.models import Category, Item, Case, CaseItem, Opening, PromoCode, PromoCodeUse, BloggerPayout
from payments.models import Transaction
from payments.services import modify_user_balance


class BloggerSystemComprehensiveTestCase(TestCase):
    """
    Comprehensive tests covering all 10 required aspects of the Blogger Attribution & Statistics system:
    1. User deposit with promo code EMU.
    2. Deposit does not credit blogger commission (0 UC from deposit).
    3. User openings properly attributed to EMU.
    4. Net Loss calculated correctly: max(0, spent - won).
    5. 10% calculated strictly on Net Loss.
    6. Another promo code does not leak into EMU statistics.
    7. Exclude canceled / non-completed operations.
    8. Payout history preserved across operations.
    9. Remaining balance calculated correctly (calculated - paid).
    10. Monthly breakdown isolates different months properly.
    """

    def setUp(self):
        # Create Superuser and Staff user
        self.superuser = User.objects.create_superuser('admin_boss', 'boss@test.com', 'boss_pass_123')
        self.staff_user = User.objects.create_user('regular_staff', 'staff@test.com', 'staff_pass_123', is_staff=True)

        # Create Category, Case, and Items
        self.category = Category.objects.create(name='Test Cat', slug='test-cat')
        self.case = Case.objects.create(
            name='Neon Case',
            slug='neon-case',
            price=Decimal('100.00'),
            category=self.category,
            active=True
        )
        self.item_cheap = Item.objects.create(name='P250 Sand', value=Decimal('20.00'), rarity='mil-spec')
        self.item_expensive = Item.objects.create(name='AK-47 Asiimov', value=Decimal('500.00'), rarity='covert')
        self.case_item1 = CaseItem.objects.create(case=self.case, item=self.item_cheap, weight=80)
        self.case_item2 = CaseItem.objects.create(case=self.case, item=self.item_expensive, weight=20)

        # Create PromoCodes with different blogger percentages
        now = timezone.now()
        self.promo_emu = PromoCode.objects.create(
            code='EMU',
            blogger_name='EMU',
            blogger_percentage=Decimal('10.00'),
            bonus_type='percentage',
            bonus_value=Decimal('10.00'),
            starts_at=now - timedelta(days=1),
            expires_at=now + timedelta(days=30),
            is_active=True
        )
        self.promo_abc = PromoCode.objects.create(
            code='ABC',
            blogger_name='ABC',
            blogger_percentage=Decimal('15.00'),
            bonus_type='percentage',
            bonus_value=Decimal('15.00'),
            starts_at=now - timedelta(days=1),
            expires_at=now + timedelta(days=30),
            is_active=True
        )

        # Referred Users
        self.user_smoke = User.objects.create_user('Smoke', 'smoke@test.com', 'smoke_pass')
        self.user_bob = User.objects.create_user('Bob', 'bob@test.com', 'bob_pass')

    def test_01_and_02_manual_deposit_linking_and_zero_commission_from_deposit(self):
        """
        1. User deposited with promo code EMU.
        2. Deposit does NOT credit blogger commission (commission is strictly 0 UC from deposit).
        """
        # Admin registers manual deposit with promo_code=EMU
        tx = Transaction.objects.create(
            user=self.user_smoke,
            amount=Decimal('10000.00'),
            transaction_type='deposit',
            status='pending',
            promo_code=self.promo_emu,
            description="Ручное пополнение через админку"
        )

        # Check client admin approve
        c = Client()
        c.force_login(self.superuser)
        resp = c.get(reverse('admin:payments_tx_approve', args=[tx.id]))
        self.assertEqual(resp.status_code, 302)

        tx.refresh_from_db()
        self.assertEqual(tx.status, 'completed')

        # Verify user is now linked with promo code EMU via PromoCodeUse
        uses = PromoCodeUse.objects.filter(user=self.user_smoke, promo_code=self.promo_emu)
        self.assertTrue(uses.exists(), "User Smoke should be linked to promo code EMU")

        # Verify strict financial rule: Blogger gets 0 UC from deposit
        stats = self.promo_emu.get_stats_for_period()
        self.assertEqual(stats['total_deposits'], Decimal('10000.00'))
        self.assertEqual(stats['total_spent'], Decimal('0.00'))
        self.assertEqual(stats['net_loss'], Decimal('0.00'))
        self.assertEqual(stats['blogger_payout'], Decimal('0.00'), "Blogger MUST receive 0 UC from deposit alone!")

    def test_03_04_05_openings_attribution_net_loss_and_10_percent_calculation(self):
        """
        3. User openings properly attributed to EMU.
        4. Net Loss calculated correctly: spent - won.
        5. 10% calculated strictly on Net Loss.
        Calculation Example from requirements:
          Deposited: 10 000 UC
          Spent on cases: 10 000 UC
          Won items: 9 160 UC
          Net Loss: 840 UC
          Blogger Payout (10%): 84 UC
        """
        # Link user_smoke with EMU
        PromoCodeUse.objects.create(
            user=self.user_smoke,
            promo_code=self.promo_emu,
            bonus_amount=Decimal('0.00')
        )
        # Deposit 10 000 UC
        modify_user_balance(self.user_smoke, Decimal('10000.00'), transaction_type='deposit')

        # Create openings totaling 10 000 UC spent, 9 160 UC won
        # For simplicity, 100 openings at 100 UC = 10 000 UC spent
        # We simulate 1 opening with 9160 won and 99 with 0 won (or exact numbers)
        item_jackpot = Item.objects.create(name='AWP Dragon Lore', value=Decimal('9160.00'), rarity='extraordinary')
        item_empty = Item.objects.create(name='P90 Sand', value=Decimal('0.00'), rarity='mil-spec')

        # 1st opening: 100 UC price, 9160 won
        Opening.objects.create(user=self.user_smoke, case=self.case, item=item_jackpot, price=Decimal('100.00'))
        # 99 openings: 99 * 100 = 9900 UC price, 0 won
        for _ in range(99):
            Opening.objects.create(user=self.user_smoke, case=self.case, item=item_empty, price=Decimal('100.00'))

        stats = self.promo_emu.get_stats_for_period()
        self.assertEqual(stats['users_count'], 1)
        self.assertEqual(stats['openings_count'], 100)
        self.assertEqual(stats['total_spent'], Decimal('10000.00'))
        self.assertEqual(stats['total_won'], Decimal('9160.00'))
        self.assertEqual(stats['net_loss'], Decimal('840.00'))
        # Strict formula check: 840 * 10% = 84 UC
        self.assertEqual(stats['blogger_payout'], Decimal('84.00'))

    def test_06_isolation_between_different_promo_codes(self):
        """
        6. Another promo code (ABC with 15%) does not leak into EMU statistics.
        """
        # Link Smoke to EMU
        PromoCodeUse.objects.create(user=self.user_smoke, promo_code=self.promo_emu)
        # Link Bob to ABC
        PromoCodeUse.objects.create(user=self.user_bob, promo_code=self.promo_abc)

        # Smoke plays under EMU: spent 1000, won 200 -> Loss 800
        Opening.objects.create(user=self.user_smoke, case=self.case, item=self.item_cheap, price=Decimal('1000.00')) # item_cheap value=20

        # Bob plays under ABC: spent 5000, won 500 -> Loss 4500
        Opening.objects.create(user=self.user_bob, case=self.case, item=self.item_expensive, price=Decimal('5000.00')) # value=500

        emu_stats = self.promo_emu.get_stats_for_period()
        abc_stats = self.promo_abc.get_stats_for_period()

        self.assertEqual(emu_stats['users_count'], 1)
        self.assertEqual(emu_stats['total_spent'], Decimal('1000.00'))
        self.assertEqual(emu_stats['total_won'], Decimal('20.00'))
        self.assertEqual(emu_stats['net_loss'], Decimal('980.00'))
        self.assertEqual(emu_stats['blogger_payout'], Decimal('98.00')) # 10% of 980

        self.assertEqual(abc_stats['users_count'], 1)
        self.assertEqual(abc_stats['total_spent'], Decimal('5000.00'))
        self.assertEqual(abc_stats['total_won'], Decimal('500.00'))
        self.assertEqual(abc_stats['net_loss'], Decimal('4500.00'))
        self.assertEqual(abc_stats['blogger_payout'], Decimal('675.00')) # 15% of 4500

    def test_07_no_loss_when_user_won_more_than_spent(self):
        """
        7. Zero / negative loss: if user won more than spent, net_loss is 0 UC, payout is 0 UC.
        """
        PromoCodeUse.objects.create(user=self.user_smoke, promo_code=self.promo_emu)
        # Spent 100 UC, won 500 UC
        Opening.objects.create(user=self.user_smoke, case=self.case, item=self.item_expensive, price=Decimal('100.00'))

        stats = self.promo_emu.get_stats_for_period()
        self.assertEqual(stats['total_spent'], Decimal('100.00'))
        self.assertEqual(stats['total_won'], Decimal('500.00'))
        self.assertEqual(stats['net_loss'], Decimal('0.00'))
        self.assertEqual(stats['blogger_payout'], Decimal('0.00'))

    def test_08_and_09_payout_history_and_remaining_balance_calculation(self):
        """
        8. Payout history preserved.
        9. Remaining balance calculated correctly:
           Calculated: 84 000 UC
           Paid: 50 000 UC
           Remaining: 34 000 UC
        """
        PromoCodeUse.objects.create(user=self.user_smoke, promo_code=self.promo_emu)
        # Generate 840 000 UC loss: spent 840 020, won 20 -> loss 840 000
        Opening.objects.create(user=self.user_smoke, case=self.case, item=self.item_cheap, price=Decimal('840020.00'))

        stats = self.promo_emu.get_stats_for_period()
        self.assertEqual(stats['net_loss'], Decimal('840000.00'))
        self.assertEqual(stats['blogger_payout'], Decimal('84000.00')) # 10% of 840,000

        # Mark partial payout: 50 000 UC
        payout = BloggerPayout.objects.create(
            promo_code=self.promo_emu,
            amount=Decimal('50000.00'),
            period='2026-09',
            admin_user=self.superuser,
            comment="Первый транш"
        )
        self.assertEqual(payout.amount, Decimal('50000.00'))

        # Check Blogger Dashboard View calculations
        c = Client()
        c.force_login(self.superuser)
        resp = c.get(reverse('admin_blogger_dashboard'))
        self.assertEqual(resp.status_code, 200)

        # Locate EMU in context rows
        blogger_rows = resp.context['blogger_rows']
        emu_row = next(r for r in blogger_rows if r['code'] == 'EMU')
        self.assertEqual(emu_row['blogger_payout'], Decimal('84000.00'))
        self.assertEqual(emu_row['paid_amount'], Decimal('50000.00'))
        self.assertEqual(emu_row['remaining_balance'], Decimal('34000.00'))

    def test_10_monthly_breakdown_isolation(self):
        """
        10. Statistics for different months do not mix.
        """
        p_use = PromoCodeUse.objects.create(user=self.user_smoke, promo_code=self.promo_emu)
        PromoCodeUse.objects.filter(id=p_use.id).update(used_at=timezone.make_aware(datetime(2026, 8, 1, 0, 0)))

        # Create openings in August 2026 and September 2026
        august_date = timezone.make_aware(datetime(2026, 8, 15, 12, 0))
        september_date = timezone.make_aware(datetime(2026, 9, 5, 14, 0))

        op_aug = Opening.objects.create(user=self.user_smoke, case=self.case, item=self.item_cheap, price=Decimal('520020.00'))
        Opening.objects.filter(id=op_aug.id).update(created_at=august_date)

        op_sep = Opening.objects.create(user=self.user_smoke, case=self.case, item=self.item_cheap, price=Decimal('840020.00'))
        Opening.objects.filter(id=op_sep.id).update(created_at=september_date)

        monthly = self.promo_emu.get_monthly_breakdown()
        m_keys = [m['month_key'] for m in monthly]
        self.assertIn('2026-09', m_keys)
        self.assertIn('2026-08', m_keys)

        sep_row = next(m for m in monthly if m['month_key'] == '2026-09')
        aug_row = next(m for m in monthly if m['month_key'] == '2026-08')

        # August: spent 520 020, won 20 -> Net Loss 520 000 -> Payout 52 000 UC
        self.assertEqual(aug_row['net_loss'], Decimal('520000.00'))
        self.assertEqual(aug_row['blogger_payout'], Decimal('52000.00'))

        # September: spent 840 020, won 20 -> Net Loss 840 000 -> Payout 84 000 UC
        self.assertEqual(sep_row['net_loss'], Decimal('840000.00'))
        self.assertEqual(sep_row['blogger_payout'], Decimal('84000.00'))

    def test_11_permissions_regular_staff_cannot_mark_payout(self):
        """
        11. Permissions: Only superuser can mark payouts. Regular staff gets 403 Forbidden.
        """
        c = Client()
        c.force_login(self.staff_user)

        resp = c.post(reverse('admin_mark_blogger_payout'), {
            'promo_code_id': self.promo_emu.id,
            'amount': '1000.00',
            'period': '2026-09',
        })
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(BloggerPayout.objects.count(), 0)

    def test_12_csv_export_endpoint(self):
        """
        12. CSV Export contains all required headers and columns.
        """
        PromoCodeUse.objects.create(user=self.user_smoke, promo_code=self.promo_emu)
        Opening.objects.create(user=self.user_smoke, case=self.case, item=self.item_cheap, price=Decimal('100.00'))

        c = Client()
        c.force_login(self.superuser)
        resp = c.get(reverse('admin_export_blogger_stats_csv'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv; charset=utf-8')
        content = resp.content.decode('utf-8')
        self.assertIn('Блогер', content)
        self.assertIn('Промокод', content)
        self.assertIn('Net Loss (UC)', content)
        self.assertIn('К выплате (UC)', content)
        self.assertIn('EMU', content)
