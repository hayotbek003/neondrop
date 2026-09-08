import shutil
from pathlib import Path
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.conf import settings
from cases.models import Case, Item, CaseItem, Category
from cases.image_importer import (
    extract_lamborghini_items_from_grid,
    import_or_update_items,
    LAMBORGHINI_ITEMS_METADATA
)
from cases.rtp_calculator import calculate_rtp_chances, validate_case_chances


class Command(BaseCommand):
    help = "Creates or updates the «Lamborghini» case (5,000 UC) with 24 items cropped from the grid screenshot."

    def add_arguments(self, parser):
        parser.add_argument(
            '--mode',
            type=str,
            default='power_law',
            choices=['power_law', 'monotonic', 'balanced', 'high_volatility'],
            help='Calculation mode: power_law, monotonic, balanced or high_volatility'
        )
        parser.add_argument(
            '--target-rtp',
            type=float,
            default=0.80,
            help='Target RTP as decimal (e.g. 0.80 for 80%) or percentage (e.g. 80)'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Explicitly force recreation or updating of existing case and chances'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("\n======================================================="))
        self.stdout.write(self.style.NOTICE("  NEONDROP: Setting up Case «Lamborghini» (5000 UC)"))
        self.stdout.write(self.style.NOTICE("=======================================================\n"))

        case_price = Decimal("5000.00")
        raw_target_rtp = options.get('target_rtp', 0.80)
        target_rtp = raw_target_rtp / 100.0 if raw_target_rtp > 1.0 else raw_target_rtp
        calc_mode = options['mode']

        # Safety Guard: Check if case already exists and has items
        existing_case = Case.objects.filter(slug='lamborghini').first()
        if not existing_case:
            existing_case = Case.objects.filter(name="Lamborghini").first()

        if existing_case and not options.get('force'):
            items_count = existing_case.case_items.count()
            if items_count == 24:
                cis = list(existing_case.case_items.select_related('item').all())
                tot_w = sum(ci.weight for ci in cis)
                if tot_w > 0:
                    ev = sum((ci.weight / tot_w) * float(ci.item.value) for ci in cis)
                    rtp = (ev / float(existing_case.price)) * 100.0 if existing_case.price > 0 else 0
                    if abs(rtp - (target_rtp * 100.0)) < 0.5:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"[OK] Case «{existing_case.name}» already has all 24 items and verified {rtp:.2f}% RTP (Price: {existing_case.price} UC).\n"
                                f"Zero modification policy: skipping. Pass --force to overwrite."
                            )
                        )
                        return

        # Find cover and grid image
        resources_dir = Path(settings.BASE_DIR) / 'cases' / 'resources'
        brain_dir = Path("C:/Users/User/.gemini/antigravity/brain/9c5f3916-a635-4e03-934c-0fd82e1bb1c1/.user_uploaded")

        grid_image = resources_dir / "lamborghini_grid.png"
        if not grid_image.exists():
            grid_image = brain_dir / "media_1788900017685.png"

        cover_image = resources_dir / "lamborghini_cover.jpg"
        if not cover_image.exists():
            cover_image = brain_dir / "media_1788900016334.jpg"

        media_cases_dir = Path(settings.MEDIA_ROOT) / 'cases'
        media_cases_dir.mkdir(parents=True, exist_ok=True)
        static_cases_dir = Path(settings.BASE_DIR) / 'static' / 'cases'
        static_cases_dir.mkdir(parents=True, exist_ok=True)

        media_items_dir = Path(settings.MEDIA_ROOT) / 'items'
        media_items_dir.mkdir(parents=True, exist_ok=True)

        # 1. Setup cover artwork
        case_cover_rel = 'cases/lamborghini.jpg'
        if cover_image.exists():
            shutil.copyfile(cover_image, media_cases_dir / 'lamborghini.jpg')
            shutil.copyfile(cover_image, static_cases_dir / 'lamborghini.jpg')
            self.stdout.write(self.style.SUCCESS(f" [OK] Case artwork saved to: {case_cover_rel}"))
        else:
            self.stdout.write(self.style.WARNING(f" [NOTICE] Cover image not found at {cover_image}"))

        # 2. Extract and crop individual item artworks from screenshot
        if grid_image.exists():
            self.stdout.write(" -> Extracting and cropping 24 item icons from grid screenshot...")
            processed_data = extract_lamborghini_items_from_grid(grid_image, output_dir=media_items_dir)
            self.stdout.write(self.style.SUCCESS(f" [OK] Successfully cropped {len(processed_data)} item images!"))
        else:
            self.stdout.write(self.style.WARNING(" -> Screenshot file not found, using preset metadata..."))
            processed_data = LAMBORGHINI_ITEMS_METADATA

        # 3. Create or update Item records in database
        self.stdout.write(" -> Importing items into database without duplication...")
        db_items = import_or_update_items(processed_data)
        self.stdout.write(self.style.SUCCESS(f" [OK] Total items in database: {Item.objects.count()} (added/verified {len(db_items)})"))

        # 4. Calculate RTP chances for 5000 UC case
        items_for_calc = []
        for it in db_items:
            meta = next((m for m in LAMBORGHINI_ITEMS_METADATA if m["name"] == it.name), None)
            val = meta["value"] if meta else it.value
            items_for_calc.append({
                'id': it.id,
                'name': it.name,
                'value': float(val),
                'item_obj': it
            })

        self.stdout.write(f" -> Calculating mathematical RTP chances (Target RTP: {round(target_rtp*100, 1)}%, Price: {case_price} UC, Mode: {calc_mode})...")
        rtp_result = calculate_rtp_chances(items_for_calc, case_price, target_rtp=target_rtp, mode=calc_mode)

        valid, msg = validate_case_chances(rtp_result['items'])
        if not valid:
            self.stdout.write(self.style.ERROR(f" [ERROR] Chance validation failed: {msg}"))
            return

        self.stdout.write(self.style.SUCCESS(f" [OK] Chance distribution verified: {msg}"))

        # 5. Create or update Case «Lamborghini»
        category, _ = Category.objects.get_or_create(
            name="Кейсы со скинами",
            defaults={'slug': 'cases-with-skins', 'order': 1}
        )

        case_obj, created = Case.objects.get_or_create(
            slug="lamborghini",
            defaults={
                'name': 'Lamborghini',
                'category': category,
                'price': case_price,
                'active': True,
                'is_popular': True,
                'is_new': True,
                'color_theme': 'godlike-gold',
                'image': case_cover_rel
            }
        )

        if not created:
            case_obj.name = "Lamborghini"
            case_obj.price = case_price
            case_obj.active = True
            case_obj.is_popular = True
            case_obj.is_new = True
            case_obj.color_theme = 'godlike-gold'
            if not case_obj.image:
                case_obj.image = case_cover_rel
            case_obj.save()

        # 6. Populate CaseItem containments
        CaseItem.objects.filter(case=case_obj).delete()
        for it_data in rtp_result['items']:
            item_model = it_data['item_obj']
            chance_weight = it_data['weight']
            CaseItem.objects.create(
                case=case_obj,
                item=item_model,
                weight=chance_weight
            )

        # 7. Print summary table
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(f"  CASE «{case_obj.name.upper()}» READY")
        self.stdout.write("=" * 80)
        self.stdout.write(f"  Case Price:       {case_obj.price} UC")
        self.stdout.write(f"  Target RTP:       {rtp_result['target_rtp']}%")
        self.stdout.write(f"  Calculated RTP:   {rtp_result['calculated_rtp']}%")
        self.stdout.write(f"  Expected Return:  {rtp_result['expected_return']} UC")
        self.stdout.write(f"  House Edge:       {rtp_result['house_edge']}%")
        self.stdout.write(f"  Total Prob:       {rtp_result['total_probability']}%")
        self.stdout.write("-" * 80)
        self.stdout.write(f"  {'ITEM NAME':<37} | {'TIER':<10} | {'PRICE (UC)':<10} | {'CHANCE %':<10}")
        self.stdout.write("-" * 80)

        for it in sorted(rtp_result['items'], key=lambda x: -x['value']):
            self.stdout.write(f"  {it['name']:<37} | {it['tier']:<10} | {it['value']:>8.2f} UC | {it['chance']:>7.3f}%")

        self.stdout.write("=" * 80 + "\n")
