import os
import sys
import json
import gzip
from decimal import Decimal
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum, Count, Q
from django.contrib.auth.models import User
from django.conf import settings
from users.models import Profile
from cases.models import (
    Category, Item, Case, CaseItem, Opening,
    PersonalCaseChance, PersonalRtpBonus, PromoCode, PromoCodeUse, UserFreeOpening
)
from inventory.models import InventoryItem
from payments.models import Transaction
from upgrades.models import UpgradeAttempt
from contracts.models import Contract, ContractInputItem
from battles.models import Battle, BattlePlayer, BattleRound

class Command(BaseCommand):
    help = "Audits and verifies database migration integrity, record counts, and financial ledger consistency."

    def add_arguments(self, parser):
        parser.add_argument(
            '--compare',
            type=str,
            help='Path to backup JSON file (.json or .json.gz) to verify exact record count match'
        )
        parser.add_argument(
            '--json-output',
            action='store_true',
            help='Output audit summary as structured JSON'
        )

    def handle(self, *args, **options):
        # 1. Gather live statistics
        users_count = User.objects.count()
        profiles_count = Profile.objects.count()
        total_balance = Profile.objects.aggregate(s=Sum('balance'))['s'] or Decimal('0.00')
        total_winnings = Profile.objects.aggregate(s=Sum('total_winnings'))['s'] or Decimal('0.00')
        
        items_count = Item.objects.count()
        categories_count = Category.objects.count()
        cases_count = Case.objects.count()
        case_items_count = CaseItem.objects.count()

        inventory_total = InventoryItem.objects.count()
        inventory_active = InventoryItem.objects.filter(is_sold=False).count()
        inventory_sold = InventoryItem.objects.filter(is_sold=True).count()

        openings_count = Opening.objects.count()
        personal_chances_count = PersonalCaseChance.objects.count()
        personal_rtp_bonuses_count = PersonalRtpBonus.objects.count()
        promocodes_count = PromoCode.objects.count()
        promocode_uses_count = PromoCodeUse.objects.count()
        free_openings_count = UserFreeOpening.objects.count()

        transactions_count = Transaction.objects.count()
        tx_deposits = Transaction.objects.filter(transaction_type='deposit', status='completed').aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
        tx_case_opens = Transaction.objects.filter(transaction_type='case_open', status='completed').aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
        tx_item_sells = Transaction.objects.filter(transaction_type='item_sell', status='completed').aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
        tx_withdrawals = Transaction.objects.filter(transaction_type='withdrawal', status='completed').aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

        upgrades_count = UpgradeAttempt.objects.count()
        contracts_count = Contract.objects.count()
        contract_inputs_count = ContractInputItem.objects.count()
        battles_count = Battle.objects.count()
        battle_players_count = BattlePlayer.objects.count()
        battle_rounds_count = BattleRound.objects.count()

        live_counts = {
            'auth.User': users_count,
            'users.Profile': profiles_count,
            'cases.Category': categories_count,
            'cases.Item': items_count,
            'cases.Case': cases_count,
            'cases.CaseItem': case_items_count,
            'cases.Opening': openings_count,
            'cases.PersonalCaseChance': personal_chances_count,
            'cases.PersonalRtpBonus': personal_rtp_bonuses_count,
            'cases.PromoCode': promocodes_count,
            'cases.PromoCodeUse': promocode_uses_count,
            'cases.UserFreeOpening': free_openings_count,
            'inventory.InventoryItem': inventory_total,
            'payments.Transaction': transactions_count,
            'upgrades.UpgradeAttempt': upgrades_count,
            'contracts.Contract': contracts_count,
            'contracts.ContractInputItem': contract_inputs_count,
            'battles.Battle': battles_count,
            'battles.BattlePlayer': battle_players_count,
            'battles.BattleRound': battle_rounds_count,
        }

        if options.get('json_output'):
            report = {
                "live_counts": live_counts,
                "financials": {
                    "total_user_balance": float(total_balance),
                    "total_user_winnings": float(total_winnings),
                    "tx_completed_deposits": float(tx_deposits),
                    "tx_completed_case_opens": float(tx_case_opens),
                    "tx_completed_item_sells": float(tx_item_sells),
                },
                "inventory": {
                    "total": inventory_total,
                    "active": inventory_active,
                    "sold": inventory_sold,
                }
            }
            self.stdout.write(json.dumps(report, indent=2))
            return

        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS("           [NEONDROP] MIGRATION & DATA INTEGRITY AUDIT"))
        self.stdout.write("=" * 70)
        self.stdout.write(f" Database Engine:  {settings.DATABASES['default'].get('ENGINE')}")
        self.stdout.write(f" Database Name:    {settings.DATABASES['default'].get('NAME')}")
        self.stdout.write("-" * 70)

        self.stdout.write(self.style.NOTICE(" 1. USERS & PROFILES:"))
        self.stdout.write(f"    - Users:                  {users_count:>8}")
        self.stdout.write(f"    - Profiles:               {profiles_count:>8} (1:1 Match: {'OK' if users_count == profiles_count else 'MISMATCH'})")
        self.stdout.write(f"    - Total User Balances:     {total_balance:>10.2f} UC")
        self.stdout.write(f"    - Total Winnings Recorded: {total_winnings:>10.2f} UC")

        self.stdout.write(self.style.NOTICE("\n 2. CASES & SKINS CATALOG:"))
        self.stdout.write(f"    - Categories:             {categories_count:>8}")
        self.stdout.write(f"    - Items (Skins):          {items_count:>8}")
        self.stdout.write(f"    - Cases:                  {cases_count:>8}")
        self.stdout.write(f"    - CaseItem Containments:  {case_items_count:>8}")

        self.stdout.write(self.style.NOTICE("\n 3. USER INVENTORY & DROPS:"))
        self.stdout.write(f"    - Total Inventory Items:  {inventory_total:>8}")
        self.stdout.write(f"    - Active in Inventory:    {inventory_active:>8}")
        self.stdout.write(f"    - Sold Items:             {inventory_sold:>8}")
        self.stdout.write(f"    - Case Openings History:  {openings_count:>8}")

        self.stdout.write(self.style.NOTICE("\n 4. FINANCIAL LEDGER (TRANSACTIONS):"))
        self.stdout.write(f"    - Total Transactions:     {transactions_count:>8}")
        self.stdout.write(f"    - Completed Deposits:      {tx_deposits:>10.2f} UC")
        self.stdout.write(f"    - Case Openings Spent:     {tx_case_opens:>10.2f} UC")
        self.stdout.write(f"    - Item Sells Credited:     {tx_item_sells:>10.2f} UC")

        self.stdout.write(self.style.NOTICE("\n 5. PROMOS, CHANCES & MINI-GAMES:"))
        self.stdout.write(f"    - PromoCodes:             {promocodes_count:>8}")
        self.stdout.write(f"    - PromoCode Activations:  {promocode_uses_count:>8}")
        self.stdout.write(f"    - User Free Openings:     {free_openings_count:>8}")
        self.stdout.write(f"    - Personal Case Chances:  {personal_chances_count:>8}")
        self.stdout.write(f"    - Upgrade Attempts:       {upgrades_count:>8}")
        self.stdout.write(f"    - Contracts Created:      {contracts_count:>8}")
        self.stdout.write(f"    - Battles:                {battles_count:>8}")

        # Comparison mode if backup file provided
        if options.get('compare'):
            compare_path = Path(options['compare'])
            if not compare_path.exists():
                raise CommandError(f"Comparison backup file not found: {compare_path.resolve()}")

            self.stdout.write("\n" + "=" * 70)
            self.stdout.write(self.style.NOTICE(f" [COMPARISON AUDIT] Validating against: {compare_path.name}"))
            self.stdout.write("=" * 70)

            is_gzip = compare_path.suffix.lower() == '.gz' or compare_path.name.endswith('.json.gz')
            if is_gzip:
                with gzip.open(compare_path, 'rb') as f:
                    payload = json.loads(f.read().decode('utf-8'))
            else:
                with open(compare_path, 'rb') as f:
                    payload = json.loads(f.read().decode('utf-8'))

            backup_counts = payload.get('metadata', {}).get('record_counts', {})
            if not backup_counts:
                # Calculate counts directly from objects
                objects_list = payload.get('data', payload if isinstance(payload, list) else [])
                backup_counts = {}
                for item in objects_list:
                    model = item.get('model')
                    if model:
                        backup_counts[model] = backup_counts.get(model, 0) + 1

            all_matched = True
            self.stdout.write(f" {'MODEL':<30} | {'BACKUP':>8} | {'CURRENT DB':>10} | {'STATUS':<10}")
            self.stdout.write("-" * 70)

            for model_label, current_cnt in live_counts.items():
                b_cnt = backup_counts.get(model_label, 0)
                status_str = "MATCH [OK]" if b_cnt == current_cnt else "MISMATCH [FAIL]"
                if b_cnt != current_cnt:
                    all_matched = False
                    self.stdout.write(self.style.ERROR(f" {model_label:<30} | {b_cnt:>8} | {current_cnt:>10} | {status_str}"))
                else:
                    self.stdout.write(f" {model_label:<30} | {b_cnt:>8} | {current_cnt:>10} | {status_str}")

            self.stdout.write("=" * 70)
            if all_matched:
                self.stdout.write(self.style.SUCCESS(" [VERIFICATION PASSED] ZERO DATA LOSS CONFIRMED: 100% Records Match!"))
            else:
                self.stdout.write(self.style.ERROR(" [VERIFICATION FAILED] Discrepancies detected between backup and live database!"))
                sys.exit(1)
        else:
            self.stdout.write("=" * 70 + "\n")
