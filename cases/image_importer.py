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
    Parses a 6-column x 4-row grid image, crops individual item artworks,
    and returns a list of recognized items with local cropped image paths.
    """
    img_path = Path(image_path)
    if not img_path.exists():
        raise FileNotFoundError(f"Image not found: {img_path}")

    if output_dir is None:
        target_dir = Path(settings.MEDIA_ROOT) / 'items'
    else:
        target_dir = Path(output_dir)

    target_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(img_path) as img:
        img_w, img_h = img.size

        # Standard bounding box offsets for header and grid
        # Header "Содержимое кейса..." occupies top ~7-10%
        top_offset = int(img_h * 0.08)
        bottom_offset = int(img_h * 0.03)
        left_offset = int(img_w * 0.01)
        right_offset = int(img_w * 0.01)

        grid_w = img_w - (left_offset + right_offset)
        grid_h = img_h - (top_offset + bottom_offset)

        cols = 6
        rows = 4
        cell_w = grid_w / cols
        cell_h = grid_h / rows

        processed_items = []
        seen_names = set()

        for meta in PARADISE_ITEMS_METADATA:
            name = meta["name"]
            if name in seen_names:
                continue
            seen_names.add(name)

            r = meta["row"]
            c = meta["col"]

            # Compute cell coordinates
            x1 = int(left_offset + c * cell_w)
            y1 = int(top_offset + r * cell_h)
            x2 = int(left_offset + (c + 1) * cell_w)
            y2 = int(top_offset + (r + 1) * cell_h)

            # Inside the card, the icon is in the upper 65% of the card
            card_crop_h = y2 - y1
            icon_y2 = int(y1 + card_crop_h * 0.65)

            # Crop item preview
            icon_img = img.crop((x1 + 4, y1 + 4, x2 - 4, icon_y2))

            # Save individual item image
            filename = f"{meta['slug']}.png"
            file_dest = target_dir / filename
            icon_img.save(file_dest, "PNG")

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
