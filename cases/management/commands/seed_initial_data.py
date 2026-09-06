import os
from decimal import Decimal
import secrets
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from cases.models import Category, Item, Case, CaseItem, Opening
from inventory.models import InventoryItem
from users.models import Profile


class Command(BaseCommand):
    help = (
        "MANUAL-ONLY command to seed initial default cases and skins for fresh installations. "
        "This command is NEVER executed automatically during deploy to protect all admin modifications."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Explicitly force seeding even if cases already exist in the database.'
        )

    def handle(self, *args, **options):
        cases_count = Case.objects.count()
        items_count = Item.objects.count()

        if (cases_count > 0 or items_count > 0) and not options.get('force'):
            self.stdout.write(
                self.style.WARNING(
                    f"\n[NEONDROP SEED PROTECT] Database already contains {cases_count} cases and {items_count} items.\n"
                    f"To prevent overwriting admin-created cases, custom prices, and user modifications, seeding was aborted.\n"
                    f"If you intentionally want to run seeding anyway, pass the `--force` flag:\n"
                    f"  python manage.py seed_initial_data --force\n"
                )
            )
            return

        self.stdout.write(self.style.NOTICE("\n[NEONDROP] Seeding default cases and weapon skins dataset..."))

        # 1. Categories
        cat_popular, _ = Category.objects.get_or_create(name="Популярные", slug="popular", defaults={'order': 1})
        cat_new, _ = Category.objects.get_or_create(name="Новые", slug="new", defaults={'order': 2})
        cat_affordable, _ = Category.objects.get_or_create(name="Доступные", slug="affordable", defaults={'order': 3})
        cat_expensive, _ = Category.objects.get_or_create(name="Дорогие", slug="expensive", defaults={'order': 4})

        # 2. Items / Skins (CS:GO Cyberpunk themed)
        skins_data = [
            # Knives & Exotics
            ('Karambit', 'Fade', Decimal('1450.00'), 'knife', 'knife_karambit_fade'),
            ('Butterfly Knife', 'Doppler', Decimal('1650.00'), 'knife', 'knife_butterfly_doppler'),
            ('M9 Bayonet', 'Gamma Doppler', Decimal('1350.00'), 'knife', 'knife_m9_gamma'),
            
            # Covert (Red)
            ('M4A4', 'Howl', Decimal('1850.00'), 'covert', 'm4a4_howl'),
            ('AWP', 'Dragon Lore', Decimal('2100.00'), 'covert', 'awp_dragon_lore'),
            ('AK-47', 'Neon Rider', Decimal('42.31'), 'covert', 'ak47_neon_rider'),
            ('M4A4', 'The Emperor', Decimal('25.41'), 'covert', 'm4a4_the_emperor'),
            ('USP-S', 'Kill Confirmed', Decimal('75.00'), 'covert', 'usps_kill_confirmed'),
            ('AK-47', 'Asiimov', Decimal('48.50'), 'covert', 'ak47_asiimov'),

            # Classified (Pink)
            ('AWP', 'Containment Breach', Decimal('98.11'), 'classified', 'awp_containment_breach'),
            ('AWP', 'Neo-Noir', Decimal('38.50'), 'classified', 'awp_neo_noir'),
            ('M4A1-S', 'Hyper Beast', Decimal('24.18'), 'classified', 'm4a1s_hyper_beast'),
            ('USP-S', 'Cortex', Decimal('18.73'), 'classified', 'usps_cortex'),
            ('AK-47', 'Redline', Decimal('19.80'), 'classified', 'ak47_redline'),
            ('AWP', 'Hyper Beast', Decimal('35.00'), 'classified', 'awp_hyper_beast'),

            # Restricted (Purple)
            ('Desert Eagle', 'Printstream', Decimal('56.23'), 'restricted', 'deagle_printstream'),
            ('Glock-18', 'Water Elemental', Decimal('11.50'), 'restricted', 'glock18_water_elemental'),
            ('M4A4', 'Neo-Noir', Decimal('14.20'), 'restricted', 'm4a4_neo_noir'),
            ('USP-S', 'Neo-Noir', Decimal('16.80'), 'restricted', 'usps_neo_noir'),
            ('AK-47', 'Phantom Disruptor', Decimal('12.50'), 'restricted', 'ak47_phantom_disruptor'),

            # Mil-Spec (Blue)
            ('P90', 'Asiimov', Decimal('15.23'), 'mil_spec', 'p90_asiimov'),
            ('SG 553', 'Cyrex', Decimal('7.43'), 'mil_spec', 'sg553_cyrex'),
            ('Glock-18', 'Vogue', Decimal('6.50'), 'mil_spec', 'glock18_vogue'),
            ('M4A1-S', 'Flashback', Decimal('4.80'), 'mil_spec', 'm4a1s_flashback'),
            ('Desert Eagle', 'Light Rail', Decimal('3.90'), 'mil_spec', 'deagle_light_rail'),
            ('USP-S', 'Cyrex', Decimal('3.20'), 'mil_spec', 'usps_cyrex'),
            ('MP9', 'Starlight Protector', Decimal('2.90'), 'mil_spec', 'mp9_starlight'),
        ]

        items_map = {}
        for wpn, skn, val, rarity, img_key in skins_data:
            item, _ = Item.objects.get_or_create(
                weapon_type=wpn,
                skin_name=skn,
                defaults={
                    'value': val,
                    'rarity': rarity,
                    'image_url': img_key,
                }
            )
            items_map[f"{wpn} | {skn}"] = item

        # 3. Cases
        cases_data = [
            {
                'name': 'Neon Case',
                'slug': 'neon-case',
                'price': Decimal('2.49'),
                'color_theme': 'neon-green',
                'category': cat_popular,
                'is_popular': True,
                'is_new': False,
                'order': 1,
                'items': [
                    ('Karambit | Fade', 0.05),
                    ('AK-47 | Neon Rider', 0.5),
                    ('USP-S | Cortex', 3.0),
                    ('Desert Eagle | Printstream', 6.0),
                    ('Glock-18 | Water Elemental', 15.0),
                    ('SG 553 | Cyrex', 35.0),
                    ('USP-S | Cyrex', 40.45),
                ]
            },
            {
                'name': 'Cyber Case',
                'slug': 'cyber-case',
                'price': Decimal('4.99'),
                'color_theme': 'cyber-pink',
                'category': cat_popular,
                'is_popular': True,
                'is_new': True,
                'order': 2,
                'items': [
                    ('Karambit | Fade', 0.02),
                    ('M4A4 | Howl', 0.2),
                    ('AK-47 | Neon Rider', 0.5),
                    ('AWP | Neo-Noir', 1.5),
                    ('M4A1-S | Hyper Beast', 3.0),
                    ('USP-S | Cortex', 5.0),
                    ('Desert Eagle | Printstream', 15.0),
                    ('P90 | Asiimov', 25.0),
                    ('SG 553 | Cyrex', 49.78),
                ]
            },
            {
                'name': 'Galaxy Case',
                'slug': 'galaxy-case',
                'price': Decimal('9.99'),
                'color_theme': 'galaxy-purple',
                'category': cat_popular,
                'is_popular': True,
                'is_new': False,
                'order': 3,
                'items': [
                    ('Butterfly Knife | Doppler', 0.08),
                    ('AWP | Containment Breach', 2.0),
                    ('AK-47 | Asiimov', 4.0),
                    ('AWP | Neo-Noir', 8.0),
                    ('Desert Eagle | Printstream', 18.0),
                    ('P90 | Asiimov', 30.0),
                    ('Glock-18 | Vogue', 37.92),
                ]
            },
            {
                'name': 'Frost Case',
                'slug': 'frost-case',
                'price': Decimal('19.99'),
                'color_theme': 'frost-cyan',
                'category': cat_popular,
                'is_popular': True,
                'is_new': False,
                'order': 4,
                'items': [
                    ('M9 Bayonet | Gamma Doppler', 0.15),
                    ('AWP | Dragon Lore', 0.35),
                    ('AWP | Containment Breach', 5.0),
                    ('M4A1-S | Hyper Beast', 12.0),
                    ('Desert Eagle | Printstream', 25.0),
                    ('AK-47 | Redline', 30.0),
                    ('M4A1-S | Flashback', 27.5),
                ]
            },
            {
                'name': 'Demon Case',
                'slug': 'demon-case',
                'price': Decimal('39.99'),
                'color_theme': 'demon-orange',
                'category': cat_popular,
                'is_popular': True,
                'is_new': False,
                'order': 5,
                'items': [
                    ('Butterfly Knife | Doppler', 0.5),
                    ('M4A4 | Howl', 1.0),
                    ('USP-S | Kill Confirmed', 8.5),
                    ('Desert Eagle | Printstream', 20.0),
                    ('AK-47 | Neon Rider', 30.0),
                    ('AWP | Hyper Beast', 40.0),
                ]
            },
            {
                'name': 'Godlike Case',
                'slug': 'godlike-case',
                'price': Decimal('99.99'),
                'color_theme': 'godlike-gold',
                'category': cat_expensive,
                'is_popular': True,
                'is_new': True,
                'order': 6,
                'items': [
                    ('Karambit | Fade', 2.0),
                    ('AWP | Dragon Lore', 3.0),
                    ('M4A4 | Howl', 5.0),
                    ('AWP | Containment Breach', 25.0),
                    ('USP-S | Kill Confirmed', 35.0),
                    ('AK-47 | Asiimov', 30.0),
                ]
            },
            {
                'name': 'Luxury Case',
                'slug': 'luxury-case',
                'price': Decimal('199.99'),
                'color_theme': 'luxury-silver',
                'category': cat_expensive,
                'is_popular': False,
                'is_new': False,
                'order': 7,
                'items': [
                    ('Karambit | Fade', 5.0),
                    ('Butterfly Knife | Doppler', 6.0),
                    ('AWP | Dragon Lore', 8.0),
                    ('M4A4 | Howl', 10.0),
                    ('AWP | Containment Breach', 40.0),
                    ('USP-S | Kill Confirmed', 31.0),
                ]
            },
            {
                'name': 'Supreme Case',
                'slug': 'supreme-case',
                'price': Decimal('499.99'),
                'color_theme': 'supreme-red',
                'category': cat_expensive,
                'is_popular': False,
                'is_new': True,
                'order': 8,
                'items': [
                    ('AWP | Dragon Lore', 15.0),
                    ('M4A4 | Howl', 20.0),
                    ('Butterfly Knife | Doppler', 25.0),
                    ('Karambit | Fade', 40.0),
                ]
            },
        ]

        for cd in cases_data:
            case, _ = Case.objects.get_or_create(
                slug=cd['slug'],
                defaults={
                    'name': cd['name'],
                    'price': cd['price'],
                    'color_theme': cd['color_theme'],
                    'category': cd['category'],
                    'is_popular': cd['is_popular'],
                    'is_new': cd['is_new'],
                    'order': cd['order'],
                    'image_url': f"case_{cd['slug'].replace('-', '_')}",
                }
            )
            for skin_name, weight in cd['items']:
                if skin_name in items_map:
                    CaseItem.objects.get_or_create(
                        case=case,
                        item=items_map[skin_name],
                        defaults={'weight': weight}
                    )

        self.stdout.write(self.style.SUCCESS(f"[OK] Seeded {len(cases_data)} cases and {len(items_map)} items."))
