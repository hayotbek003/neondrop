import os
import re
from pathlib import Path
from decimal import Decimal
from PIL import Image

from django.conf import settings
from django.utils.text import slugify
from cases.models import Item, Category


# Definition of the 24 items in the 6x4 grid of «Райское извержение»
PARADISE_ITEMS_METADATA = [
    # Row 1 (Cols 1-6)
    {
        "row": 0, "col": 0,
        "name": "Gilded Glowing Parachute",
        "weapon_type": "Parachute",
        "skin_name": "Gilded Glowing",
        "rarity": "covert",
        "value": Decimal("120.00"),
        "tier": "Jackpot",
        "slug": "gilded-glowing-parachute"
    },
    {
        "row": 0, "col": 1,
        "name": "Mega Kitty Parachute",
        "weapon_type": "Parachute",
        "skin_name": "Mega Kitty",
        "rarity": "classified",
        "value": Decimal("60.00"),
        "tier": "Legendary",
        "slug": "mega-kitty-parachute"
    },
    {
        "row": 0, "col": 2,
        "name": "Blueyonder Glider",
        "weapon_type": "Glider",
        "skin_name": "Blueyonder",
        "rarity": "covert",
        "value": Decimal("150.00"),
        "tier": "Jackpot",
        "slug": "blueyonder-glider"
    },
    {
        "row": 0, "col": 3,
        "name": "Boxerbolt Hoverboard",
        "weapon_type": "Hoverboard",
        "skin_name": "Boxerbolt",
        "rarity": "classified",
        "value": Decimal("75.00"),
        "tier": "Legendary",
        "slug": "boxerbolt-hoverboard"
    },
    {
        "row": 0, "col": 4,
        "name": "Crimson Fox Set",
        "weapon_type": "Clothes",
        "skin_name": "Crimson Fox",
        "rarity": "classified",
        "value": Decimal("55.00"),
        "tier": "Legendary",
        "slug": "crimson-fox-set"
    },
    {
        "row": 0, "col": 5,
        "name": "Space Mascot Headpiece",
        "weapon_type": "Clothes",
        "skin_name": "Space Mascot",
        "rarity": "restricted",
        "value": Decimal("25.00"),
        "tier": "Rare",
        "slug": "space-mascot-headpiece"
    },

    # Row 2 (Cols 1-6)
    {
        "row": 1, "col": 0,
        "name": "Crimson Fox - Pan",
        "weapon_type": "Pan",
        "skin_name": "Crimson Fox",
        "rarity": "covert",
        "value": Decimal("180.00"),
        "tier": "Jackpot",
        "slug": "crimson-fox-pan"
    },
    {
        "row": 1, "col": 1,
        "name": "Past Glory Set",
        "weapon_type": "Clothes",
        "skin_name": "Past Glory",
        "rarity": "restricted",
        "value": Decimal("20.00"),
        "tier": "Rare",
        "slug": "past-glory-set"
    },
    {
        "row": 1, "col": 2,
        "name": "Bloody Bite - DP28",
        "weapon_type": "DP-28",
        "skin_name": "Bloody Bite",
        "rarity": "restricted",
        "value": Decimal("35.00"),
        "tier": "Rare",
        "slug": "bloody-bite-dp28"
    },
    {
        "row": 1, "col": 3,
        "name": "The Fangs Set",
        "weapon_type": "Clothes",
        "skin_name": "The Fangs",
        "rarity": "restricted",
        "value": Decimal("22.00"),
        "tier": "Rare",
        "slug": "the-fangs-set"
    },
    {
        "row": 1, "col": 4,
        "name": "Masked Psychic Cover",
        "weapon_type": "Clothes",
        "skin_name": "Masked Psychic",
        "rarity": "restricted",
        "value": Decimal("12.00"),
        "tier": "Rare",
        "slug": "masked-psychic-cover"
    },
    {
        "row": 1, "col": 5,
        "name": "Octosurprise Backpack",
        "weapon_type": "Backpack",
        "skin_name": "Octosurprise",
        "rarity": "restricted",
        "value": Decimal("30.00"),
        "tier": "Rare",
        "slug": "octosurprise-backpack"
    },

    # Row 3 (Cols 1-6)
    {
        "row": 2, "col": 0,
        "name": "Obsidian Eagle Mask",
        "weapon_type": "Clothes",
        "skin_name": "Obsidian Eagle",
        "rarity": "restricted",
        "value": Decimal("18.00"),
        "tier": "Rare",
        "slug": "obsidian-eagle-mask"
    },
    {
        "row": 2, "col": 1,
        "name": "Blood Raven Parachute",
        "weapon_type": "Parachute",
        "skin_name": "Blood Raven",
        "rarity": "restricted",
        "value": Decimal("14.00"),
        "tier": "Rare",
        "slug": "blood-raven-parachute"
    },
    {
        "row": 2, "col": 2,
        "name": "Neptune's Grasp - Crowbar",
        "weapon_type": "Crowbar",
        "skin_name": "Neptune's Grasp",
        "rarity": "restricted",
        "value": Decimal("16.00"),
        "tier": "Rare",
        "slug": "neptunes-grasp-crowbar"
    },
    {
        "row": 2, "col": 3,
        "name": "Winter Wonderland - Sickle",
        "weapon_type": "Sickle",
        "skin_name": "Winter Wonderland",
        "rarity": "restricted",
        "value": Decimal("15.00"),
        "tier": "Rare",
        "slug": "winter-wonderland-sickle"
    },
    {
        "row": 2, "col": 4,
        "name": "Nightscape Gladiator - PP-19 Bizon",
        "weapon_type": "PP-19 Bizon",
        "skin_name": "Nightscape Gladiator",
        "rarity": "restricted",
        "value": Decimal("28.00"),
        "tier": "Rare",
        "slug": "nightscape-gladiator-pp19"
    },
    {
        "row": 2, "col": 5,
        "name": "Hellfire UAZ",
        "weapon_type": "Vehicle",
        "skin_name": "Hellfire",
        "rarity": "restricted",
        "value": Decimal("50.00"),
        "tier": "Legendary",
        "slug": "hellfire-uaz"
    },

    # Row 4 (Cols 1-6)
    {
        "row": 3, "col": 0,
        "name": "Wonderland Traveler - UMP45",
        "weapon_type": "UMP45",
        "skin_name": "Wonderland Traveler",
        "rarity": "mil_spec",
        "value": Decimal("5.00"),
        "tier": "Common",
        "slug": "wonderland-traveler-ump45"
    },
    {
        "row": 3, "col": 1,
        "name": "Classic Santa Suit",
        "weapon_type": "Clothes",
        "skin_name": "Classic Santa",
        "rarity": "mil_spec",
        "value": Decimal("4.00"),
        "tier": "Common",
        "slug": "classic-santa-suit"
    },
    {
        "row": 3, "col": 2,
        "name": "Iron Judge Hat",
        "weapon_type": "Clothes",
        "skin_name": "Iron Judge",
        "rarity": "mil_spec",
        "value": Decimal("2.00"),
        "tier": "Common",
        "slug": "iron-judge-hat"
    },
    {
        "row": 3, "col": 3,
        "name": "Phantom Fox Mask",
        "weapon_type": "Clothes",
        "skin_name": "Phantom Fox",
        "rarity": "mil_spec",
        "value": Decimal("3.00"),
        "tier": "Common",
        "slug": "phantom-fox-mask"
    },
    {
        "row": 3, "col": 4,
        "name": "Shadowfire Captain - Kar98K",
        "weapon_type": "Kar98K",
        "skin_name": "Shadowfire Captain",
        "rarity": "mil_spec",
        "value": Decimal("8.00"),
        "tier": "Uncommon",
        "slug": "shadowfire-captain-kar98k"
    },
    {
        "row": 3, "col": 5,
        "name": "Illusion Judge - Pan",
        "weapon_type": "Pan",
        "skin_name": "Illusion Judge",
        "rarity": "mil_spec",
        "value": Decimal("7.00"),
        "tier": "Uncommon",
        "slug": "illusion-judge-pan"
    },
]


def extract_items_from_grid_image(image_path, output_dir=None):
    """
    Parses a 6-column x 4-row grid image, crops individual item artworks with precise
    centering, contrast enhancement, Lanczos scaling, and smooth rounded corners.
    Returns a list of recognized items with local cropped image paths.
    """
    import numpy as np
    from PIL import ImageEnhance, ImageFilter, ImageDraw

    img_path = Path(image_path)
    if not img_path.exists():
        raise FileNotFoundError(f"Image not found: {img_path}")

    if output_dir is None:
        target_dir = Path(settings.MEDIA_ROOT) / 'items'
    else:
        target_dir = Path(output_dir)

    target_dir.mkdir(parents=True, exist_ok=True)
    static_items_dir = Path(settings.BASE_DIR) / 'static' / 'items'
    static_items_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(img_path) as img:
        img_rgba = img.convert('RGBA')
        arr = np.array(img_rgba)

        row_bounds = [(35, 119), (124, 208), (213, 297), (301, 385)]
        col_bounds = [
            (13, 168),
            (173, 329),
            (334, 489),
            (495, 650),
            (655, 811),
            (816, 972)
        ]

        processed_items = []
        seen_names = set()

        for meta in PARADISE_ITEMS_METADATA:
            name = meta["name"]
            if name in seen_names:
                continue
            seen_names.add(name)

            r = meta["row"]
            c = meta["col"]
            slug = meta["slug"]

            y1, y2 = row_bounds[r]
            x1, x2 = col_bounds[c]
            card = arr[y1:y2, x1:x2].copy()

            if r == 3 and c in (4, 5):
                card[0:18, 0:76] = [27, 28, 29, 255]
                sub = card[16:54, 45:110]
                bg = np.array([27, 28, 29], dtype=float)
                diff = np.linalg.norm(sub[:, :, :3].astype(float) - bg, axis=2)
                mask = diff > 6
                sub_y0, sub_x0 = 16, 45
            else:
                sub = card[10:52, 20:135]
                bg_l = sub[:, 0:3, :3].mean(axis=1).astype(float)
                bg_r = sub[:, -3:, :3].mean(axis=1).astype(float)
                bg = (bg_l + bg_r) / 2.0
                diff = np.linalg.norm(sub[:, :, :3].astype(float) - bg[:, None, :3], axis=2)
                mask = diff > 10
                sub_y0, sub_x0 = 10, 20

            rows, cols = np.where(mask)
            if not len(rows):
                card_ymin, card_ymax = 10, 52
                card_xmin, card_xmax = 20, 135
            else:
                card_ymin = rows.min() + sub_y0
                card_ymax = rows.max() + sub_y0
                card_xmin = cols.min() + sub_x0
                card_xmax = cols.max() + sub_x0

            center_x = (card_xmin + card_xmax) / 2.0
            center_y = (card_ymin + card_ymax) / 2.0
            box_w = card_xmax - card_xmin
            box_h = card_ymax - card_ymin

            side = max(box_w, box_h) + 6
            side = min(side, card.shape[0] - 8, card.shape[1] - 8)

            half = side / 2.0
            sq_x1 = int(round(center_x - half))
            sq_y1 = int(round(center_y - half))
            sq_x2 = int(round(center_x + half))
            sq_y2 = int(round(center_y + half))

            if sq_x1 < 4:
                sq_x2 += (4 - sq_x1)
                sq_x1 = 4
            if sq_x2 > card.shape[1] - 4:
                sq_x1 -= (sq_x2 - (card.shape[1] - 4))
                sq_x2 = card.shape[1] - 4
            if sq_y1 < 6:
                sq_y2 += (6 - sq_y1)
                sq_y1 = 6
            if sq_y2 > card.shape[0] - 6:
                sq_y1 -= (sq_y2 - (card.shape[0] - 6))
                sq_y2 = card.shape[0] - 6

            crop_sq = Image.fromarray(card[sq_y1:sq_y2, sq_x1:sq_x2])

            if slug in ('shadowfire-captain-kar98k', 'blood-raven-parachute', 'iron-judge-hat', 'illusion-judge-pan'):
                crop_sq = ImageEnhance.Brightness(crop_sq).enhance(1.25)
                crop_sq = ImageEnhance.Contrast(crop_sq).enhance(1.35)

            scaled = crop_sq.resize((240, 240), Image.Resampling.LANCZOS)
            scaled = ImageEnhance.Sharpness(scaled).enhance(1.3)

            mask_shape = Image.new('L', (240, 240), 0)
            draw = ImageDraw.Draw(mask_shape)
            draw.rounded_rectangle([(0, 0), (240, 240)], radius=24, fill=255)
            mask_shape = mask_shape.filter(ImageFilter.GaussianBlur(radius=0.75))

            canvas = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
            canvas.paste(scaled, (8, 8), mask_shape)

            filename = f"{slug}.png"
            file_dest = target_dir / filename
            canvas.save(file_dest, "PNG")

            # Also save to static/items so it is tracked in Git and survives restarts
            static_dest = static_items_dir / filename
            canvas.save(static_dest, "PNG")

            item_info = dict(meta)
            item_info["image_relative_path"] = f"items/{filename}"
            item_info["image_full_path"] = str(file_dest)
            item_info["status"] = "recognized"
            processed_items.append(item_info)

    return processed_items


def import_or_update_items(items_data):
    """
    Saves or updates Item objects in Django database without duplication.
    """
    created_items = []
    for data in items_data:
        name = data["name"]
        item = Item.objects.filter(name=name).first()

        image_rel = data.get("image_relative_path")

        if item is None:
            item = Item.objects.create(
                name=name,
                weapon_type=data.get("weapon_type", "Weapon"),
                skin_name=data.get("skin_name", name),
                rarity=data.get("rarity", "mil_spec"),
                value=Decimal(str(data.get("value", "10.00"))),
                image=image_rel if image_rel else None
            )
        else:
            # Update image if missing
            if not item.image and image_rel:
                item.image = image_rel
                item.save(update_fields=['image'])

        created_items.append(item)

    return created_items
