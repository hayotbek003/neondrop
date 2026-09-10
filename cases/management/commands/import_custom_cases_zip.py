import io
import json
import zipfile
import shutil
from pathlib import Path
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.core.files.base import ContentFile
from django.db import transaction
from django.conf import settings
from django.utils.text import slugify

from cases.models import Case, Item, CaseItem, Category
from cases.rtp_calculator import calculate_rtp_chances


class Command(BaseCommand):
    help = "Imports custom cases, items, chances and images from a ZIP archive (e.g. neondrop_cases_import.zip)."

    def add_arguments(self, parser):
        parser.add_argument(
            'zip_path',
            nargs='?',
            type=str,
            default=None,
            help='Path to the cases ZIP archive'
        )
        parser.add_argument(
            '--chances-mode',
            type=str,
            default='as_is',
            choices=['as_is', 'solve_rtp', 'recalc_rtp'],
            help=(
                "Mode for setting drop chances: "
                "'as_is' = exact chance_percent from cases.json; "
                "'solve_rtp' = balance top items #13 and #14 to exactly 100%% sum and target RTP; "
                "'recalc_rtp' = recalculate all chances via NEONDROP rtp_calculator"
            )
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Overwrite existing cases and items if they already exist'
        )

    def handle(self, *args, **options):
        zip_arg = options.get('zip_path')
        candidates = [
            Path(zip_arg) if zip_arg else None,
            Path(settings.BASE_DIR) / 'cases' / 'resources' / 'neondrop_cases_import.zip',
            Path.home() / 'Downloads' / 'neondrop_cases_import.zip',
            Path(r'C:\Users\User\Downloads\neondrop_cases_import.zip'),
        ]
        actual_zip = None
        for cand in candidates:
            if cand and cand.exists() and zipfile.is_zipfile(cand):
                actual_zip = cand
                break

        chances_mode = options['chances_mode']
        force = options['force']
        resource_json = Path(settings.BASE_DIR) / 'cases' / 'resources' / 'supercars_cases.json'

        if not actual_zip and not resource_json.exists():
            raise CommandError("Архив с кейсами не найден ни в аргументах, ни в папке Downloads, ни в cases/resources.")

        source_name = actual_zip.name if actual_zip else resource_json.name
        self.stdout.write(self.style.NOTICE("\n======================================================="))
        self.stdout.write(self.style.NOTICE(f"  NEONDROP: Импорт кейсов из источника: {source_name}"))
        self.stdout.write(self.style.NOTICE(f"  Режим шансов: {chances_mode}"))
        self.stdout.write(self.style.NOTICE("=======================================================\n"))

        zf = zipfile.ZipFile(actual_zip, 'r') if actual_zip else None
        try:
            if zf:
                namelist = zf.namelist()
                cases_json_candidates = [n for n in namelist if n.endswith('cases.json')]
                if not cases_json_candidates:
                    raise CommandError("В архиве отсутствует файл cases.json.")
                cases_data = json.loads(zf.read(cases_json_candidates[0]).decode('utf-8'))
            else:
                namelist = []
                cases_data = json.loads(resource_json.read_text(encoding='utf-8'))

            # Destination directories for media and static
            media_cases_dir = Path(settings.MEDIA_ROOT) / 'cases'
            media_cases_dir.mkdir(parents=True, exist_ok=True)
            static_cases_dir = Path(settings.BASE_DIR) / 'static' / 'cases'
            static_cases_dir.mkdir(parents=True, exist_ok=True)

            # Category: expensive
            expensive_cat = Category.objects.filter(slug='expensive').first()
            if not expensive_cat:
                expensive_cat = Category.objects.create(name='Дорогие кейсы', slug='expensive', order=4)

            # Color theme mapping for the 6 supercar cases
            theme_map = {
                'porsche-911-gt3-rs': 'godlike-gold',
                'rolls-royce': 'luxury-silver',
                'mclaren': 'demon-orange',
                'ferrari': 'supreme-red',
                'bugatti': 'cyber-pink',
                'cars-supercars': 'frost-cyan',
            }

            stats = {
                'cases_created': 0,
                'cases_existing': 0,
                'items_created': 0,
                'items_existing': 0,
                'case_items_created': 0,
                'case_items_updated': 0,
                'images_saved': 0,
            }

            with transaction.atomic():
                for case_idx, c_dict in enumerate(cases_data, 1):
                    raw_name = c_dict['name']
                    case_price = Decimal(str(c_dict.get('price_uc', 0)))
                    target_rtp_pct = float(c_dict.get('target_rtp_percent', 80))
                    case_slug = slugify(raw_name)
                    case_theme = theme_map.get(case_slug, 'cyber-pink')

                    # 1. Create or get Case
                    existing_case = Case.objects.filter(slug=case_slug).first()
                    if not existing_case:
                        existing_case = Case.objects.filter(name__iexact=raw_name).first()

                    if existing_case and not force:
                        case_obj = existing_case
                        stats['cases_existing'] += 1
                        self.stdout.write(self.style.WARNING(f" [EXISTING] Кейс «{raw_name}» уже существует (ID: {case_obj.id})."))
                    else:
                        if existing_case:
                            case_obj = existing_case
                            case_obj.name = raw_name
                            case_obj.price = case_price
                            case_obj.category = expensive_cat
                            case_obj.color_theme = case_theme
                            case_obj.active = True
                            case_obj.is_new = True
                            case_obj.save()
                            stats['cases_existing'] += 1
                            self.stdout.write(self.style.NOTICE(f" [UPDATE] Обновлён существующий кейс «{raw_name}» (ID: {case_obj.id})."))
                        else:
                            case_obj = Case(
                                name=raw_name,
                                slug=case_slug,
                                price=case_price,
                                category=expensive_cat,
                                color_theme=case_theme,
                                active=True,
                                is_new=True,
                                is_popular=True,
                                order=100 + case_idx,
                            )
                            case_obj.save()
                            stats['cases_created'] += 1
                            self.stdout.write(self.style.SUCCESS(f" [NEW] Создан кейс «{raw_name}» (ID: {case_obj.id}, Цена: {case_price} UC)."))

                    # 2. Extract and attach case image
                    img_path_in_zip = c_dict.get('image', '')
                    clean_img_path = img_path_in_zip.replace('\\', '/').lstrip('/')
                    actual_zip_img = None
                    for n in namelist:
                        if n.replace('\\', '/').lstrip('/') == clean_img_path or n.endswith(clean_img_path):
                            actual_zip_img = n
                            break

                    if actual_zip_img:
                        img_bytes = zf.read(actual_zip_img)
                        ext = Path(actual_zip_img).suffix or '.jpg'
                        filename = f"{case_slug}{ext}"
                        clean_filename = f"{case_slug.replace('-', '_')}{ext}"

                        # Save to Case.image via ContentFile
                        case_obj.image.save(filename, ContentFile(img_bytes), save=True)

                        # Also save to static/cases/ for fallback
                        with open(static_cases_dir / filename, 'wb') as sf:
                            sf.write(img_bytes)
                        if clean_filename != filename:
                            with open(static_cases_dir / clean_filename, 'wb') as sf:
                                sf.write(img_bytes)

                        stats['images_saved'] += 1
                        self.stdout.write(self.style.SUCCESS(f"  -> Изображение кейса сохранено: cases/{filename}"))
                    elif (static_cases_dir / f"{case_slug}.jpg").exists():
                        filename = f"{case_slug}.jpg"
                        img_bytes = (static_cases_dir / filename).read_bytes()
                        case_obj.image.save(filename, ContentFile(img_bytes), save=True)
                        stats['images_saved'] += 1
                        self.stdout.write(self.style.SUCCESS(f"  -> Изображение кейса скопировано из static: cases/{filename}"))
                    elif not case_obj.image:
                        case_obj.image = f"cases/{case_slug}.jpg"
                        case_obj.save(update_fields=['image'])
                    else:
                        self.stdout.write(self.style.WARNING(f"  -> Изображение '{img_path_in_zip}' не найдено в архиве."))

                    # 3. Process items and calculate chances
                    items_list = c_dict.get('items', [])

                    # Compute chances according to chances_mode
                    chances_to_assign = []
                    if chances_mode == 'as_is':
                        # Use exact numbers from JSON
                        chances_to_assign = [float(it.get('chance_percent', 0.0)) for it in items_list]

                    elif chances_mode == 'solve_rtp':
                        # Keep base items as-is, solve last two items to match target RTP and 100% total
                        base_items = items_list[:-2] if len(items_list) >= 2 else items_list
                        last_two = items_list[-2:] if len(items_list) >= 2 else []

                        target_ev = float(case_price) * (target_rtp_pct / 100.0)
                        cur_ev = sum(float(it.get('price_uc', 0)) * (float(it.get('chance_percent', 0)) / 100.0) for it in base_items)
                        cur_ch = sum(float(it.get('chance_percent', 0)) for it in base_items)
                        missing_ch = max(0.0, 100.0 - cur_ch)
                        needed_ev = target_ev - cur_ev

                        if len(last_two) == 2:
                            val13 = float(last_two[0].get('price_uc', 25000)) / 100.0
                            val14 = float(last_two[1].get('price_uc', 45000)) / 100.0
                            if val14 != val13:
                                ch14 = (needed_ev - val13 * missing_ch) / (val14 - val13)
                                ch13 = missing_ch - ch14
                            else:
                                ch13 = missing_ch / 2.0
                                ch14 = missing_ch / 2.0

                            if ch13 < 0:
                                ch14 += ch13
                                ch13 = 0.001
                                ch14 = max(0.001, missing_ch - ch13)

                            chances_to_assign = [float(it.get('chance_percent', 0.0)) for it in base_items]
                            chances_to_assign.append(round(ch13, 6))
                            chances_to_assign.append(round(ch14, 6))
                        else:
                            chances_to_assign = [float(it.get('chance_percent', 0.0)) for it in items_list]

                    elif chances_mode == 'recalc_rtp':
                        items_for_calc = [{'name': it['name'], 'value': float(it['price_uc'])} for it in items_list]
                        calc_res = calculate_rtp_chances(
                            items=items_for_calc,
                            case_price=float(case_price),
                            target_rtp=target_rtp_pct / 100.0,
                            mode='balanced'
                        )
                        chances_to_assign = [it_calc['chance'] for it_calc in calc_res['items']]

                    # Rarity mapping helper
                    rarity_map = {
                        'common': ('common', '#B0C3D9'),
                        'uncommon': ('uncommon', '#5E98D9'),
                        'rare': ('rare', '#4B69FF'),
                        'epic': ('epic', '#D32CE6'),
                        'legendary': ('legendary', '#EB4B4B'),
                        'mythic': ('mythic', '#FFD700'),
                    }

                    total_assigned_weight = 0.0
                    total_expected_return = 0.0

                    for item_idx, it_data in enumerate(items_list):
                        it_name = it_data['name'].strip()
                        it_price = Decimal(str(it_data.get('price_uc', 0)))
                        raw_rarity = str(it_data.get('rarity', 'Common')).strip().lower()
                        rarity_code, rarity_hex = rarity_map.get(raw_rarity, ('common', '#B0C3D9'))

                        assigned_weight = chances_to_assign[item_idx] if item_idx < len(chances_to_assign) else 0.0

                        # Find or create Item
                        item_obj = Item.objects.filter(name=it_name, game='PUBG').first()
                        if not item_obj:
                            item_obj = Item.objects.filter(name=it_name).first()

                        if not item_obj:
                            item_obj = Item(
                                name=it_name,
                                weapon_type="Supercar",
                                skin_name=it_name,
                                value=it_price,
                                rarity=rarity_code,
                                rarity_color=rarity_hex,
                                game='PUBG',
                                quality='Pristine',
                                item_type='vehicle',
                            )
                            item_obj.save()
                            stats['items_created'] += 1
                        else:
                            if force:
                                item_obj.value = it_price
                                item_obj.rarity = rarity_code
                                item_obj.rarity_color = rarity_hex
                                item_obj.save()
                            stats['items_existing'] += 1

                        # Find or create CaseItem connection
                        case_item = CaseItem.objects.filter(case=case_obj, item=item_obj).first()
                        if not case_item:
                            case_item = CaseItem(
                                case=case_obj,
                                item=item_obj,
                                weight=assigned_weight
                            )
                            case_item.save()
                            stats['case_items_created'] += 1
                        else:
                            case_item.weight = assigned_weight
                            case_item.save()
                            stats['case_items_updated'] += 1

                        total_assigned_weight += assigned_weight
                        total_expected_return += float(it_price) * (assigned_weight / 100.0)

                    actual_rtp = (total_expected_return / float(case_price) * 100.0) if case_price > 0 else 0.0

                    self.stdout.write(
                        f"  -> Привязано {len(items_list)} предметов: "
                        f"Сумма весов = {total_assigned_weight:.3f}%, "
                        f"EV = {total_expected_return:.2f} UC, "
                        f"RTP = {actual_rtp:.2f}% (Целевой: {target_rtp_pct:.1f}%)\n"
                    )

            self.stdout.write(self.style.SUCCESS("\n======================================================="))
            self.stdout.write(self.style.SUCCESS("  ИТОГИ ИМПОРТА КЕЙСОВ"))
            self.stdout.write(self.style.SUCCESS("======================================================="))
            self.stdout.write(f"  Создано новых кейсов:       {stats['cases_created']}")
            self.stdout.write(f"  Существующих кейсов:        {stats['cases_existing']}")
            self.stdout.write(f"  Создано новых предметов:    {stats['items_created']}")
            self.stdout.write(f"  Существующих предметов:     {stats['items_existing']}")
            self.stdout.write(f"  Создано связей CaseItem:    {stats['case_items_created']}")
            self.stdout.write(f"  Обновлено связей CaseItem:  {stats['case_items_updated']}")
            self.stdout.write(f"  Загружено фото кейсов:      {stats['images_saved']}")
            self.stdout.write(self.style.SUCCESS("=======================================================\n"))
        finally:
            if zf:
                zf.close()
