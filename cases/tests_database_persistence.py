import os
import tempfile
from decimal import Decimal
from django.test import TestCase, override_settings
from django.core.management import call_command
from django.contrib.auth.models import User
from django.conf import settings
from io import StringIO

from cases.models import Case, Item, CaseItem, Opening
from users.models import Profile
from payments.models import Transaction


class DatabasePersistenceTests(TestCase):
    """
    Tests verifying persistent database behavior, startup integrity checks,
    protection against data wiping on restart, and safe population of catalog.
    """

    def setUp(self):
        # Create baseline test users and cases
        self.smoke_user, _ = User.objects.get_or_create(
            username='Smoke',
            defaults={'email': 'smoke@neondrop.gg', 'is_staff': True, 'is_superuser': True}
        )
        self.smoke_profile, _ = Profile.objects.get_or_create(
            user=self.smoke_user,
            defaults={'balance': Decimal('1500.00')}
        )

        self.item1, _ = Item.objects.get_or_create(
            name='AKM Glacier',
            defaults={'weapon_type': 'AKM', 'skin_name': 'Glacier', 'value': Decimal('250.00'), 'rarity': 'covert'}
        )

        self.case1, _ = Case.objects.get_or_create(
            name='Neon Case',
            defaults={'price': Decimal('4.08'), 'active': True}
        )
        CaseItem.objects.get_or_create(
            case=self.case1,
            item=self.item1,
            defaults={'weight': 10.0}
        )

    def test_check_database_config_command_runs_successfully(self):
        """Verify check_database_config executes cleanly and reports engine and stats."""
        out = StringIO()
        call_command('check_database_config', stdout=out)
        output = out.getvalue()

        self.assertIn("NEONDROP DATABASE CONFIGURATION CHECK", output)
        self.assertIn("Engine:", output)
        self.assertIn("Connected:", output)
        self.assertIn("CURRENT RECORD COUNTS:", output)

    def test_ensure_persistent_data_protects_existing_cases(self):
        """
        When cases already exist in the database, ensure_persistent_data MUST NOT
        overwrite, reset, or alter existing records.
        """
        initial_case_count = Case.objects.count()
        self.assertGreater(initial_case_count, 0)

        out = StringIO()
        call_command('ensure_persistent_data', stdout=out)
        output = out.getvalue()

        self.assertIn("Zero data loss protection active: skipping initial data restore", output)
        self.assertEqual(Case.objects.count(), initial_case_count)

    def test_simulated_restart_preserves_custom_cases_and_data(self):
        """
        Simulate user creating a new case in Admin, then triggering a container restart.
        Verify that the new case and all data remain completely intact.
        """
        # User creates a new custom case via Admin
        custom_case = Case.objects.create(
            name="Admin Mystery Case",
            price=Decimal('77.70'),
            active=True
        )
        CaseItem.objects.create(
            case=custom_case,
            item=self.item1,
            weight=25.0
        )

        # Record pre-restart state
        pre_case_count = Case.objects.count()
        pre_item_count = Item.objects.count()
        pre_user_count = User.objects.count()
        pre_balance = Profile.objects.get(user=self.smoke_user).balance

        # Simulate Render startup sequence (as executed in start.sh)
        call_command('check_database_config', stdout=StringIO())
        call_command('ensure_persistent_data', stdout=StringIO())
        call_command('promote_admin', 'Smoke', stdout=StringIO())

        # Post-restart verification
        self.assertEqual(Case.objects.count(), pre_case_count, "Case count must remain unchanged after restart")
        self.assertEqual(Item.objects.count(), pre_item_count, "Item count must remain unchanged after restart")
        self.assertEqual(User.objects.count(), pre_user_count, "User count must remain unchanged after restart")

        # Verify custom case exists with exact same data
        persisted_case = Case.objects.filter(name="Admin Mystery Case").first()
        self.assertIsNotNone(persisted_case, "Custom case created in Admin must persist across restart")
        self.assertEqual(persisted_case.price, Decimal('77.70'))
        self.assertEqual(persisted_case.case_items.count(), 1)

        # Verify user balance remains exact
        post_balance = Profile.objects.get(user=self.smoke_user).balance
        self.assertEqual(post_balance, pre_balance, "User balances must be preserved across restart")

    def test_database_url_env_resolution_strips_quotes_and_supports_variants(self):
        """Test parsing of DATABASE_URL variants including quotes and postgres:// schemes."""
        import urllib.parse

        test_urls = [
            '"postgresql://neondrop_user:secret_pass@dpg-abc123-a.oregon-postgres.render.com:5432/neondrop"',
            "'postgres://neondrop_user:secret_pass@dpg-abc123-a:5432/neondrop'",
            "postgresql://neondrop_user:secret_pass@localhost:5432/neondrop",
        ]

        for raw_url in test_urls:
            cleaned = raw_url.strip().strip('"\'')
            if cleaned.startswith('postgres://'):
                cleaned = cleaned.replace('postgres://', 'postgresql://', 1)
            parsed = urllib.parse.urlparse(cleaned)
            self.assertEqual(parsed.scheme, 'postgresql')
            self.assertEqual(parsed.username, 'neondrop_user')
            self.assertEqual(parsed.password, 'secret_pass')
            self.assertEqual(parsed.path.lstrip('/'), 'neondrop')

    def test_context_processor_injects_db_info(self):
        """Verify user_profile_context injects db_is_persistent and db_engine_name."""
        from django.test.client import RequestFactory
        from users.context_processors import user_profile_context

        factory = RequestFactory()
        request = factory.get('/admin/')
        request.user = self.smoke_user

        ctx = user_profile_context(request)
        self.assertIn('db_is_persistent', ctx)
        self.assertIn('db_engine_name', ctx)
        self.assertIn('db_host_display', ctx)
