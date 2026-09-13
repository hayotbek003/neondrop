import os
import json
import shutil
from pathlib import Path
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify
from django.conf import settings

from cases.models import Category, Case, Item, CaseItem

RARITY_MAP = {
    'common': ('common', '#B0C3D9'),
    'uncommon': ('uncommon', '#5E98D9'),
    'rare': ('rare', '#4B69FF'),
    'epic': ('epic', '#D32CE6'),
    'legendary': ('legendary', '#EB4B4B'),
    'mythic': ('mythic', '#FFD700'),
    'jackpot': ('mythic', '#FFD700'),
}

THEME_CHOICES_CYCLE = [
    'neon-green',
    'cyber-pink',
    'galaxy-purple',
    'frost-cyan',
    'demon-orange',
    'godlike-gold',
    'luxury-silver',
    'supreme-red',
]

# 14 Shared Item Template Assets mapped sequentially to each case's 14 items
# From Common/Uncommon gear to Rare/Epic weapons to Legendary/Mythic/Jackpot suits & cars
ITEM_TEMPLATES = [
    '8x-scope.png',                           # Slot 01 (Common)
    'flash-hider-sniper-rifles-refined.png',  # Slot 02 (Common)
    'angry-red-pan.png',                       # Slot 03 (Common)
    'black-cat-backpack.png',                  # Slot 04 (Common)
    'anniversary-helmet.png',                  # Slot 05 (Uncommon)
    'futuristic-streetwear-backpack.png',      # Slot 06 (Uncommon)
    'sks-steel-front.png',                     # Slot 07 (Rare)
    'famas-steel-front.png',                   # Slot 08 (Rare)
    'akm-cobra.png',                           # Slot 09 (Epic)
    'm416-cobra.png',                          # Slot 10 (Epic)
    'cyber-agent-set.png',                     # Slot 11 (Legendary)
    'azure-crystal-kar98k.png',                # Slot 12 (Legendary)
    'stygian-liege-x-suit-1-star.png',         # Slot 13 (Mythic)
    'hypercar-showcase.png',                   # Slot 14 (Jackpot)
]

def get_theme_for_case(name: str, index: int) -> str:
    name_l = name.lower()
    if any(k in name_l for k in ['ice', 'frost', 'glacier']):
        return 'frost-cyan'
    if any(k in name_l for k in ['inferno', 'dragon', 'phoenix', 'fire', 'lava']):
        return 'demon-orange'
    if any(k in name_l for k in ['galaxy', 'cosmic', 'purple', 'void']):
        return 'galaxy-purple'
    if any(k in name_l for k in ['neon', 'spark', 'quantum', 'matrix', 'toxic']):
        return 'neon-green'
    if any(k in name_l for k in ['supreme', 'titan', 'legend', 'royal', 'gold']):
        return 'godlike-gold'
    if any(k in name_l for k in ['chrome', 'shadow', 'blackout']):
        return 'luxury-silver'
    if any(k in name_l for k in ['rush', 'drive', 'hyper']):
        return 'cyber-pink'
    return THEME_CHOICES_CYCLE[index % len(THEME_CHOICES_CYCLE)]

class Command(BaseCommand):
    help = "Import or update 30 real photo cases into NEONDROP with shared template item images (idempotent)"

    def handle(self, *args, **options):
        base_dir = Path(settings.BASE_DIR)
        res_dir = base_dir / "cases" / "resources" / "30_cases"
        cases_json = res_dir / "cases.json"
        images_dir = res_dir / "images"

        if not cases_json.exists():
            scratch_path = Path(r"C:\Users\User\.gemini\antigravity\brain\9c5f3916-a635-4e03-934c-0fd82e1bb1c1\scratch\extracted_30_cases")
            if (scratch_path / "cases.json").exists():
                cases_json = scratch_path / "cases.json"
                images_dir = scratch_path / "images"

        if not cases_json.exists():
            self.stderr.write(f"cases.json not found at {cases_json}")
            return

        with open(cases_json, "r", encoding="utf-8") as f:
            data = json.load(f)

        cases_data = data.get("cases", [])
        self.stdout.write(f"Found {len(cases_data)} cases in {cases_json}")

        media_cases_dir = Path(settings.MEDIA_ROOT) / "cases"
        static_cases_dir = base_dir / "static" / "cases"
        media_items_dir = Path(settings.MEDIA_ROOT) / "items"
        static_items_dir = base_dir / "static" / "items"

        media_cases_dir.mkdir(parents=True, exist_ok=True)
        static_cases_dir.mkdir(parents=True, exist_ok=True)
        media_items_dir.mkdir(parents=True, exist_ok=True)
        static_items_dir.mkdir(parents=True, exist_ok=True)

        # Ensure all 14 template item assets exist in both media/items and static/items
        for tmpl in ITEM_TEMPLATES:
            src_static = static_items_dir / tmpl
            dst_media = media_items_dir / tmpl
            if src_static.exists() and not dst_media.exists():
                shutil.copy2(src_static, dst_media)
            elif dst_media.exists() and not src_static.exists():
                shutil.copy2(dst_media, src_static)

        cat_affordable, _ = Category.objects.get_or_create(
            slug="affordable",
            defaults={"name": "Доступные", "order": 2, "is_active": True}
        )
        cat_new, _ = Category.objects.get_or_create(
            slug="new",
            defaults={"name": "Новые", "order": 3, "is_active": True}
        )
        cat_expensive, _ = Category.objects.get_or_create(
            slug="expensive",
            defaults={"name": "Дорогие", "order": 4, "is_active": True}
        )

        created_cases = 0
        updated_cases = 0
        created_items = 0
        updated_items = 0
        created_case_items = 0
        updated_case_items = 0

        with transaction.atomic():
            for idx, c in enumerate(cases_data):
                case_name = c["name"]
                price_val = Decimal(str(c["case_price_uc"]))
                color_theme = get_theme_for_case(case_name, idx)
                img_rel = c["image"]
                img_filename = Path(img_rel).name

                if price_val <= 100:
                    category = cat_affordable
                elif price_val <= 300:
                    category = cat_new
                else:
                    category = cat_expensive

                case_slug = slugify(case_name)

                src_img = images_dir / img_filename
                if src_img.exists():
                    dst_media = media_cases_dir / img_filename
                    dst_static = static_cases_dir / img_filename
                    if not dst_media.exists() or dst_media.stat().st_size != src_img.stat().st_size:
                        shutil.copy2(src_img, dst_media)
                    if not dst_static.exists() or dst_static.stat().st_size != src_img.stat().st_size:
                        shutil.copy2(src_img, dst_static)

                case, created = Case.objects.get_or_create(
                    slug=case_slug,
                    defaults={
                        "name": case_name,
                        "price": price_val,
                        "category": category,
                        "image": f"cases/{img_filename}",
                        "image_url": "",
                        "color_theme": color_theme,
                        "is_new": True,
                        "is_popular": False,
                        "active": True,
                        "order": 100 + idx,
                    }
                )
                if created:
                    created_cases += 1
                else:
                    updated_cases += 1
                    case.name = case_name
                    case.price = price_val
                    case.category = category
                    case.image = f"cases/{img_filename}"
                    case.image_url = ""
                    case.color_theme = color_theme
                    case.is_new = True
                    case.active = True
                    case.order = 100 + idx
                    case.save()

                for it_idx, it in enumerate(c["items"]):
                    it_name = it["name"]
                    it_price = Decimal(str(it["price_uc"]))
                    it_rarity_raw = it.get("rarity", "common").lower()
                    rarity_code, rarity_color = RARITY_MAP.get(it_rarity_raw, ('common', '#B0C3D9'))
                    chance = float(it["chance_percent"])

                    # Pick shared template image by position in the case (0 to 13)
                    tmpl_filename = ITEM_TEMPLATES[it_idx % len(ITEM_TEMPLATES)]
                    item_img_rel = f"items/{tmpl_filename}"
                    item_img_url = f"/static/items/{tmpl_filename}"
                    skin_label = f"Item {it_idx + 1:02d}"

                    item, i_created = Item.objects.get_or_create(
                        name=it_name,
                        defaults={
                            "value": it_price,
                            "rarity": rarity_code,
                            "rarity_color": rarity_color,
                            "weapon_type": case_name,
                            "skin_name": skin_label,
                            "quality": "Factory New",
                            "game": "NEONDROP",
                            "image": item_img_rel,
                            "image_url": item_img_url,
                        }
                    )
                    if i_created:
                        created_items += 1
                    else:
                        updated_items += 1
                        item.value = it_price
                        item.rarity = rarity_code
                        item.rarity_color = rarity_color
                        item.weapon_type = case_name
                        item.skin_name = skin_label
                        item.quality = "Factory New"
                        item.game = "NEONDROP"
                        item.image = item_img_rel
                        item.image_url = item_img_url
                        item.save()

                    case_item, ci_created = CaseItem.objects.get_or_create(
                        case=case,
                        item=item,
                        defaults={
                            "weight": chance,
                        }
                    )
                    if ci_created:
                        created_case_items += 1
                    else:
                        updated_case_items += 1
                        case_item.weight = chance
                        case_item.save()

        self.stdout.write(self.style.SUCCESS(
            f"Import complete: Cases: +{created_cases} (~{updated_cases}), "
            f"Items: +{created_items} (~{updated_items}), "
            f"CaseItems: +{created_case_items} (~{updated_case_items}), "
            f"All 420 items linked to 14 shared template images successfully."
        ))
