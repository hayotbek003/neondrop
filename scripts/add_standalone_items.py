"""
Standalone items importer script.
Imports items from the 5 uploaded screenshot grids into Django Item model.
Prices range from 200.00 UC to 13,694.00 UC.
Images are cropped, scaled with LANCZOS, and saved with rounded corners to media/items/ and static/items/.
NO Case is created.
"""

import os
import sys
from pathlib import Path
from decimal import Decimal

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageDraw
import cv2

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings
from django.utils.text import slugify
from cases.models import Item

UPLOADED_DIR = Path(r"C:\Users\User\.gemini\antigravity\brain\9c5f3916-a635-4e03-934c-0fd82e1bb1c1\.user_uploaded")

IMAGES_LAYOUT = {
    'im1': {
        'file': 'media_1788903116663.png',
        'row_ys': [4, 90, 176, 261],
    },
    'im2': {
        'file': 'media_1788903131085.png',
        'row_ys': [35, 120, 206, 292],
    },
    'im3': {
        'file': 'media_1788903165512.png',
        'row_ys': [59, 145, 231, 317],
    },
    'im4': {
        'file': 'media_1788903166636.png',
        'row_ys': [39, 124, 210, 295],
    },
    'im5': {
        'file': 'media_1788903184939.png',
        'row_ys': [7, 93, 178, 264],
    },
}

COLS_BOUNDS = [
    (37, 187),
    (194, 344),
    (350, 500),
    (506, 656),
    (663, 813),
    (819, 969)
]

RARITY_COLORS = {
    'knife': '#ffd700',
    'covert': '#eb4b4b',
    'classified': '#d32ce6',
    'restricted': '#8847ff',
    'mil_spec': '#4b69ff',
}

NEW_ITEMS_DATA = [
    # Top Hypercars & Mythic Vehicles (10,000 - 13,694 UC)
    {
        "name": "Bentley Flying Spur Mulliner",
        "weapon_type": "Vehicle",
        "skin_name": "Flying Spur Mulliner",
        "rarity": "covert",
        "value": Decimal("13694.00"),
        "img_key": "im5", "row": 3, "col": 5, "lock": True,
        "slug": "bentley-flying-spur-mulliner"
    },
    {
        "name": "Bugatti Veyron 16.4 (Gold)",
        "weapon_type": "Vehicle",
        "skin_name": "Veyron 16.4 (Gold)",
        "rarity": "covert",
        "value": Decimal("13200.00"),
        "img_key": "im3", "row": 0, "col": 1, "lock": False,
        "slug": "bugatti-veyron-16-4-gold"
    },
    {
        "name": "Pagani Imola (Nebula Dream)",
        "weapon_type": "Vehicle",
        "skin_name": "Imola (Nebula Dream)",
        "rarity": "covert",
        "value": Decimal("12800.00"),
        "img_key": "im1", "row": 1, "col": 1, "lock": False,
        "slug": "pagani-imola-nebula-dream"
    },
    {
        "name": "Bugatti La Voiture Noire",
        "weapon_type": "Vehicle",
        "skin_name": "La Voiture Noire",
        "rarity": "covert",
        "value": Decimal("12500.00"),
        "img_key": "im3", "row": 0, "col": 4, "lock": False,
        "slug": "bugatti-la-voiture-noire"
    },
    {
        "name": "Bugatti Veyron 16.4",
        "weapon_type": "Vehicle",
        "skin_name": "Veyron 16.4",
        "rarity": "covert",
        "value": Decimal("12000.00"),
        "img_key": "im3", "row": 0, "col": 2, "lock": False,
        "slug": "bugatti-veyron-16-4"
    },
    {
        "name": "Aston Martin Valkyrie (Racing Green)",
        "weapon_type": "Vehicle",
        "skin_name": "Valkyrie (Racing Green)",
        "rarity": "covert",
        "value": Decimal("11500.00"),
        "img_key": "im2", "row": 0, "col": 4, "lock": False,
        "slug": "aston-martin-valkyrie-racing-green"
    },
    {
        "name": "Lamborghini Urus Giallo Inti",
        "weapon_type": "Vehicle",
        "skin_name": "Urus Giallo Inti",
        "rarity": "covert",
        "value": Decimal("11000.00"),
        "img_key": "im1", "row": 3, "col": 5, "lock": True,
        "slug": "lamborghini-urus-giallo-inti"
    },
    {
        "name": "Maserati Luce Arancione",
        "weapon_type": "Vehicle",
        "skin_name": "Luce Arancione",
        "rarity": "covert",
        "value": Decimal("10500.00"),
        "img_key": "im2", "row": 1, "col": 0, "lock": False,
        "slug": "maserati-luce-arancione"
    },
    {
        "name": "Maserati MC20 Rosso Vincente",
        "weapon_type": "Vehicle",
        "skin_name": "MC20 Rosso Vincente",
        "rarity": "covert",
        "value": Decimal("10000.00"),
        "img_key": "im1", "row": 1, "col": 2, "lock": False,
        "slug": "maserati-mc20-rosso-vincente"
    },

    # Special Vehicles & X-Suits & Top Gold Weapons (6,000 - 9,800 UC)
    {
        "name": "Tesla Cybertruck (Dystopia Blue)",
        "weapon_type": "Vehicle",
        "skin_name": "Cybertruck (Dystopia Blue)",
        "rarity": "covert",
        "value": Decimal("9800.00"),
        "img_key": "im1", "row": 3, "col": 4, "lock": True,
        "slug": "tesla-cybertruck-dystopia-blue"
    },
    {
        "name": "Poseidon X-Suit (1-Star)",
        "weapon_type": "Clothes",
        "skin_name": "Poseidon X-Suit",
        "rarity": "covert",
        "value": Decimal("9500.00"),
        "img_key": "im1", "row": 1, "col": 3, "lock": False,
        "slug": "poseidon-x-suit-1-star"
    },
    {
        "name": "Silvanus X-Suit (1-Star)",
        "weapon_type": "Clothes",
        "skin_name": "Silvanus X-Suit",
        "rarity": "covert",
        "value": Decimal("9200.00"),
        "img_key": "im2", "row": 1, "col": 1, "lock": False,
        "slug": "silvanus-x-suit-1-star"
    },
    {
        "name": "Stygian Liege X-Suit (1-Star)",
        "weapon_type": "Clothes",
        "skin_name": "Stygian Liege X-Suit",
        "rarity": "classified",
        "value": Decimal("8800.00"),
        "img_key": "im3", "row": 2, "col": 1, "lock": False,
        "slug": "stygian-liege-x-suit-1-star"
    },
    {
        "name": "Wings of Fate Plane Finish",
        "weapon_type": "Vehicle",
        "skin_name": "Wings of Fate",
        "rarity": "covert",
        "value": Decimal("8500.00"),
        "img_key": "im4", "row": 0, "col": 3, "lock": False,
        "slug": "wings-of-fate-plane-finish"
    },
    {
        "name": "Serene Lumina Dacia",
        "weapon_type": "Vehicle",
        "skin_name": "Serene Lumina",
        "rarity": "covert",
        "value": Decimal("7800.00"),
        "img_key": "im1", "row": 1, "col": 0, "lock": False,
        "slug": "serene-lumina-dacia"
    },
    {
        "name": "M416 (Cobra)",
        "weapon_type": "M416",
        "skin_name": "Cobra",
        "rarity": "knife",
        "value": Decimal("7500.00"),
        "img_key": "im1", "row": 0, "col": 2, "lock": False,
        "slug": "m416-cobra"
    },
    {
        "name": "M24 (Cobra)",
        "weapon_type": "M24",
        "skin_name": "Cobra",
        "rarity": "knife",
        "value": Decimal("7200.00"),
        "img_key": "im5", "row": 0, "col": 0, "lock": False,
        "slug": "m24-cobra"
    },
    {
        "name": "MK12 (Refined)",
        "weapon_type": "MK12",
        "skin_name": "Refined",
        "rarity": "knife",
        "value": Decimal("6800.00"),
        "img_key": "im2", "row": 0, "col": 1, "lock": False,
        "slug": "mk12-refined"
    },
    {
        "name": "FAMAS (Steel Front)",
        "weapon_type": "FAMAS",
        "skin_name": "Steel Front",
        "rarity": "knife",
        "value": Decimal("6500.00"),
        "img_key": "im1", "row": 0, "col": 0, "lock": False,
        "slug": "famas-steel-front"
    },
    {
        "name": "QBZ (Steel Front)",
        "weapon_type": "QBZ",
        "skin_name": "Steel Front",
        "rarity": "knife",
        "value": Decimal("6200.00"),
        "img_key": "im1", "row": 0, "col": 1, "lock": False,
        "slug": "qbz-steel-front"
    },
    {
        "name": "MP5K (Steel Front)",
        "weapon_type": "MP5K",
        "skin_name": "Steel Front",
        "rarity": "knife",
        "value": Decimal("6000.00"),
        "img_key": "im5", "row": 0, "col": 1, "lock": False,
        "slug": "mp5k-steel-front"
    },

    # Top Gold Outfits & Gliders & Dragon Ball Characters (4,000 - 5,800 UC)
    {
        "name": "Starsea Admiral Set",
        "weapon_type": "Clothes",
        "skin_name": "Starsea Admiral",
        "rarity": "knife",
        "value": Decimal("5800.00"),
        "img_key": "im2", "row": 0, "col": 0, "lock": False,
        "slug": "starsea-admiral-set"
    },
    {
        "name": "Silver Guru Set",
        "weapon_type": "Clothes",
        "skin_name": "Silver Guru",
        "rarity": "covert",
        "value": Decimal("5600.00"),
        "img_key": "im3", "row": 3, "col": 4, "lock": True,
        "slug": "silver-guru-set"
    },
    {
        "name": "Silver Guru Cover",
        "weapon_type": "Clothes",
        "skin_name": "Silver Guru Cover",
        "rarity": "knife",
        "value": Decimal("5400.00"),
        "img_key": "im3", "row": 0, "col": 0, "lock": False,
        "slug": "silver-guru-cover"
    },
    {
        "name": "Boxerbolt Set",
        "weapon_type": "Clothes",
        "skin_name": "Boxerbolt",
        "rarity": "knife",
        "value": Decimal("5200.00"),
        "img_key": "im1", "row": 0, "col": 3, "lock": False,
        "slug": "boxerbolt-set"
    },
    {
        "name": "Flamewrath Set",
        "weapon_type": "Clothes",
        "skin_name": "Flamewrath",
        "rarity": "knife",
        "value": Decimal("5000.00"),
        "img_key": "im1", "row": 0, "col": 4, "lock": False,
        "slug": "flamewrath-set"
    },
    {
        "name": "Majestic Cavalry Cover",
        "weapon_type": "Clothes",
        "skin_name": "Majestic Cavalry",
        "rarity": "knife",
        "value": Decimal("4800.00"),
        "img_key": "im5", "row": 0, "col": 2, "lock": False,
        "slug": "majestic-cavalry-cover"
    },
    {
        "name": "Moondrop Eterna Cover",
        "weapon_type": "Clothes",
        "skin_name": "Moondrop Eterna",
        "rarity": "knife",
        "value": Decimal("4600.00"),
        "img_key": "im1", "row": 0, "col": 5, "lock": False,
        "slug": "moondrop-eterna-cover"
    },
    {
        "name": "Glacial Bride Cover",
        "weapon_type": "Clothes",
        "skin_name": "Glacial Bride",
        "rarity": "knife",
        "value": Decimal("4500.00"),
        "img_key": "im4", "row": 0, "col": 0, "lock": False,
        "slug": "glacial-bride-cover"
    },
    {
        "name": "Enchanted Carpet Glider",
        "weapon_type": "Glider",
        "skin_name": "Enchanted Carpet",
        "rarity": "covert",
        "value": Decimal("4400.00"),
        "img_key": "im5", "row": 1, "col": 4, "lock": False,
        "slug": "enchanted-carpet-glider"
    },
    {
        "name": "Myriad Prism Glider",
        "weapon_type": "Glider",
        "skin_name": "Myriad Prism",
        "rarity": "covert",
        "value": Decimal("4200.00"),
        "img_key": "im5", "row": 1, "col": 5, "lock": False,
        "slug": "myriad-prism-glider"
    },
    {
        "name": "Frieza Character Set",
        "weapon_type": "Clothes",
        "skin_name": "Frieza Character",
        "rarity": "covert",
        "value": Decimal("4000.00"),
        "img_key": "im5", "row": 1, "col": 3, "lock": False,
        "slug": "frieza-character-set"
    },
    {
        "name": "Vegeta Character Set",
        "weapon_type": "Clothes",
        "skin_name": "Vegeta Character",
        "rarity": "covert",
        "value": Decimal("4000.00"),
        "img_key": "im5", "row": 1, "col": 1, "lock": False,
        "slug": "vegeta-character-set"
    },

    # Covert Sets & Covert Helmets / Gear (1,500 - 3,800 UC)
    {
        "name": "Star Guardian Set",
        "weapon_type": "Clothes",
        "skin_name": "Star Guardian",
        "rarity": "covert",
        "value": Decimal("3800.00"),
        "img_key": "im5", "row": 0, "col": 3, "lock": False,
        "slug": "star-guardian-set"
    },
    {
        "name": "Sacred Maiden Set",
        "weapon_type": "Clothes",
        "skin_name": "Sacred Maiden",
        "rarity": "covert",
        "value": Decimal("3600.00"),
        "img_key": "im3", "row": 1, "col": 2, "lock": False,
        "slug": "sacred-maiden-set"
    },
    {
        "name": "Draconic Paladin Set",
        "weapon_type": "Clothes",
        "skin_name": "Draconic Paladin",
        "rarity": "covert",
        "value": Decimal("3500.00"),
        "img_key": "im2", "row": 1, "col": 5, "lock": False,
        "slug": "draconic-paladin-set"
    },
    {
        "name": "Mystic Sorceress Set",
        "weapon_type": "Clothes",
        "skin_name": "Mystic Sorceress",
        "rarity": "covert",
        "value": Decimal("3400.00"),
        "img_key": "im2", "row": 1, "col": 4, "lock": False,
        "slug": "mystic-sorceress-set"
    },
    {
        "name": "Tech Striker Set",
        "weapon_type": "Clothes",
        "skin_name": "Tech Striker",
        "rarity": "covert",
        "value": Decimal("3300.00"),
        "img_key": "im2", "row": 1, "col": 2, "lock": False,
        "slug": "tech-striker-set"
    },
    {
        "name": "Profane Templar Set",
        "weapon_type": "Clothes",
        "skin_name": "Profane Templar",
        "rarity": "covert",
        "value": Decimal("3200.00"),
        "img_key": "im4", "row": 0, "col": 2, "lock": False,
        "slug": "profane-templar-set"
    },
    {
        "name": "Nightscape Gladiator Set (Lv. 1)",
        "weapon_type": "Clothes",
        "skin_name": "Nightscape Gladiator",
        "rarity": "covert",
        "value": Decimal("3100.00"),
        "img_key": "im4", "row": 0, "col": 5, "lock": False,
        "slug": "nightscape-gladiator-set-lv-1"
    },
    {
        "name": "Seadream Melody Set (Lv. 1)",
        "weapon_type": "Clothes",
        "skin_name": "Seadream Melody",
        "rarity": "covert",
        "value": Decimal("3000.00"),
        "img_key": "im2", "row": 2, "col": 1, "lock": False,
        "slug": "seadream-melody-set-lv-1"
    },
    {
        "name": "Winter Guardian Set",
        "weapon_type": "Clothes",
        "skin_name": "Winter Guardian",
        "rarity": "covert",
        "value": Decimal("2900.00"),
        "img_key": "im5", "row": 1, "col": 2, "lock": False,
        "slug": "winter-guardian-set"
    },
    {
        "name": "Beta 5 Set",
        "weapon_type": "Clothes",
        "skin_name": "Beta 5",
        "rarity": "covert",
        "value": Decimal("2800.00"),
        "img_key": "im5", "row": 0, "col": 4, "lock": False,
        "slug": "beta-5-set"
    },
    {
        "name": "Midnight Muse Set",
        "weapon_type": "Clothes",
        "skin_name": "Midnight Muse",
        "rarity": "covert",
        "value": Decimal("2700.00"),
        "img_key": "im5", "row": 0, "col": 5, "lock": False,
        "slug": "midnight-muse-set"
    },
    {
        "name": "Genesis Knight Set",
        "weapon_type": "Clothes",
        "skin_name": "Genesis Knight",
        "rarity": "covert",
        "value": Decimal("2600.00"),
        "img_key": "im1", "row": 2, "col": 0, "lock": False,
        "slug": "genesis-knight-set"
    },
    {
        "name": "Molluscan Wavegazer Set",
        "weapon_type": "Clothes",
        "skin_name": "Molluscan Wavegazer",
        "rarity": "covert",
        "value": Decimal("2500.00"),
        "img_key": "im1", "row": 1, "col": 4, "lock": False,
        "slug": "molluscan-wavegazer-set"
    },
    {
        "name": "Cyber Agent Set",
        "weapon_type": "Clothes",
        "skin_name": "Cyber Agent",
        "rarity": "covert",
        "value": Decimal("2400.00"),
        "img_key": "im1", "row": 1, "col": 5, "lock": False,
        "slug": "cyber-agent-set"
    },
    {
        "name": "Battle Warden Set",
        "weapon_type": "Clothes",
        "skin_name": "Battle Warden",
        "rarity": "covert",
        "value": Decimal("2400.00"),
        "img_key": "im2", "row": 1, "col": 3, "lock": False,
        "slug": "battle-warden-set"
    },
    {
        "name": "Armored Hunter Set",
        "weapon_type": "Clothes",
        "skin_name": "Armored Hunter",
        "rarity": "covert",
        "value": Decimal("2300.00"),
        "img_key": "im3", "row": 1, "col": 3, "lock": False,
        "slug": "armored-hunter-set"
    },
    {
        "name": "Nordic Ravager Outfit",
        "weapon_type": "Clothes",
        "skin_name": "Nordic Ravager",
        "rarity": "covert",
        "value": Decimal("2200.00"),
        "img_key": "im3", "row": 1, "col": 5, "lock": False,
        "slug": "nordic-ravager-outfit"
    },
    {
        "name": "Vermilion Bird Swordsman Suit",
        "weapon_type": "Clothes",
        "skin_name": "Vermilion Bird Swordsman",
        "rarity": "covert",
        "value": Decimal("2200.00"),
        "img_key": "im3", "row": 2, "col": 0, "lock": False,
        "slug": "vermilion-bird-swordsman-suit"
    },
    {
        "name": "Anniversary Helmet",
        "weapon_type": "Helmet",
        "skin_name": "Anniversary",
        "rarity": "covert",
        "value": Decimal("2200.00"),
        "img_key": "im1", "row": 2, "col": 2, "lock": False,
        "slug": "anniversary-helmet"
    },
    {
        "name": "Noctum Sunder Helmet",
        "weapon_type": "Helmet",
        "skin_name": "Noctum Sunder",
        "rarity": "covert",
        "value": Decimal("2100.00"),
        "img_key": "im2", "row": 2, "col": 4, "lock": False,
        "slug": "noctum-sunder-helmet"
    },
    {
        "name": "Silverwing Conjurer Set",
        "weapon_type": "Clothes",
        "skin_name": "Silverwing Conjurer",
        "rarity": "covert",
        "value": Decimal("2100.00"),
        "img_key": "im2", "row": 2, "col": 0, "lock": False,
        "slug": "silverwing-conjurer-set"
    },
    {
        "name": "Silver Guru Backpack",
        "weapon_type": "Backpack",
        "skin_name": "Silver Guru",
        "rarity": "covert",
        "value": Decimal("2000.00"),
        "img_key": "im4", "row": 1, "col": 0, "lock": False,
        "slug": "silver-guru-backpack"
    },
    {
        "name": "Operation Tomorrow Set",
        "weapon_type": "Clothes",
        "skin_name": "Operation Tomorrow",
        "rarity": "covert",
        "value": Decimal("2000.00"),
        "img_key": "im2", "row": 2, "col": 3, "lock": False,
        "slug": "operation-tomorrow-set"
    },
    {
        "name": "Mowsie Set",
        "weapon_type": "Clothes",
        "skin_name": "Mowsie",
        "rarity": "covert",
        "value": Decimal("2000.00"),
        "img_key": "im1", "row": 2, "col": 1, "lock": False,
        "slug": "mowsie-set"
    },
    {
        "name": "Boxerbolt Backpack",
        "weapon_type": "Backpack",
        "skin_name": "Boxerbolt",
        "rarity": "covert",
        "value": Decimal("1900.00"),
        "img_key": "im3", "row": 1, "col": 4, "lock": False,
        "slug": "boxerbolt-backpack"
    },
    {
        "name": "Sacred Maiden Cover",
        "weapon_type": "Clothes",
        "skin_name": "Sacred Maiden Cover",
        "rarity": "covert",
        "value": Decimal("1800.00"),
        "img_key": "im5", "row": 1, "col": 0, "lock": False,
        "slug": "sacred-maiden-cover"
    },
    {
        "name": "Arctic Ruler Cover",
        "weapon_type": "Clothes",
        "skin_name": "Arctic Ruler",
        "rarity": "covert",
        "value": Decimal("1800.00"),
        "img_key": "im2", "row": 2, "col": 2, "lock": False,
        "slug": "arctic-ruler-cover"
    },
    {
        "name": "Boxerbolt Shoes",
        "weapon_type": "Clothes",
        "skin_name": "Boxerbolt Shoes",
        "rarity": "knife",
        "value": Decimal("1600.00"),
        "img_key": "im4", "row": 0, "col": 1, "lock": False,
        "slug": "boxerbolt-shoes"
    },
    {
        "name": "Illusion Judge Headgear",
        "weapon_type": "Clothes",
        "skin_name": "Illusion Judge",
        "rarity": "covert",
        "value": Decimal("1500.00"),
        "img_key": "im4", "row": 1, "col": 1, "lock": False,
        "slug": "illusion-judge-headgear"
    },

    # Classified Upgradeable Weapons & Helmets & Gear (400 - 1,500 UC)
    {
        "name": "Serpengleam Set - AWM (Lv. 1)",
        "weapon_type": "AWM",
        "skin_name": "Serpengleam",
        "rarity": "classified",
        "value": Decimal("1500.00"),
        "img_key": "im5", "row": 2, "col": 0, "lock": False,
        "slug": "serpengleam-set-awm-lv-1"
    },
    {
        "name": "Cryofrost Shard - UMP45 (Lv. 1)",
        "weapon_type": "UMP45",
        "skin_name": "Cryofrost Shard",
        "rarity": "classified",
        "value": Decimal("1400.00"),
        "img_key": "im1", "row": 2, "col": 3, "lock": False,
        "slug": "cryofrost-shard-ump45-lv-1"
    },
    {
        "name": "Wanderer - M416 (Lv. 1)",
        "weapon_type": "M416",
        "skin_name": "Wanderer",
        "rarity": "classified",
        "value": Decimal("1350.00"),
        "img_key": "im1", "row": 2, "col": 4, "lock": False,
        "slug": "wanderer-m416-lv-1"
    },
    {
        "name": "Fatal Foil - QBZ (Lv. 1)",
        "weapon_type": "QBZ",
        "skin_name": "Fatal Foil",
        "rarity": "classified",
        "value": Decimal("1300.00"),
        "img_key": "im3", "row": 2, "col": 2, "lock": False,
        "slug": "fatal-foil-qbz-lv-1"
    },
    {
        "name": "Flamewave - AWM",
        "weapon_type": "AWM",
        "skin_name": "Flamewave",
        "rarity": "classified",
        "value": Decimal("1250.00"),
        "img_key": "im1", "row": 3, "col": 0, "lock": False,
        "slug": "flamewave-awm"
    },
    {
        "name": "Silver Guru - M416",
        "weapon_type": "M416",
        "skin_name": "Silver Guru",
        "rarity": "classified",
        "value": Decimal("1200.00"),
        "img_key": "im2", "row": 2, "col": 5, "lock": False,
        "slug": "silver-guru-m416"
    },
    {
        "name": "M416 (Steel Front)",
        "weapon_type": "M416",
        "skin_name": "Steel Front",
        "rarity": "classified",
        "value": Decimal("1150.00"),
        "img_key": "im5", "row": 3, "col": 4, "lock": True,
        "slug": "m416-steel-front"
    },
    {
        "name": "Night Maiden - MG3",
        "weapon_type": "MG3",
        "skin_name": "Night Maiden",
        "rarity": "classified",
        "value": Decimal("1100.00"),
        "img_key": "im3", "row": 2, "col": 3, "lock": False,
        "slug": "night-maiden-mg3"
    },
    {
        "name": "Azure Crystal - Kar98K",
        "weapon_type": "Kar98K",
        "skin_name": "Azure Crystal",
        "rarity": "classified",
        "value": Decimal("1050.00"),
        "img_key": "im2", "row": 3, "col": 0, "lock": False,
        "slug": "azure-crystal-kar98k"
    },
    {
        "name": "Viper Assassin - M24",
        "weapon_type": "M24",
        "skin_name": "Viper Assassin",
        "rarity": "classified",
        "value": Decimal("1000.00"),
        "img_key": "im4", "row": 1, "col": 2, "lock": False,
        "slug": "viper-assassin-m24"
    },
    {
        "name": "Snowflake Girl - AKM",
        "weapon_type": "AKM",
        "skin_name": "Snowflake Girl",
        "rarity": "classified",
        "value": Decimal("950.00"),
        "img_key": "im5", "row": 2, "col": 4, "lock": False,
        "slug": "snowflake-girl-akm"
    },
    {
        "name": "Space Mascot - M762",
        "weapon_type": "M762",
        "skin_name": "Space Mascot",
        "rarity": "classified",
        "value": Decimal("900.00"),
        "img_key": "im2", "row": 3, "col": 1, "lock": False,
        "slug": "space-mascot-m762"
    },
    {
        "name": "Shadow Empress - M16A4",
        "weapon_type": "M16A4",
        "skin_name": "Shadow Empress",
        "rarity": "classified",
        "value": Decimal("880.00"),
        "img_key": "im2", "row": 3, "col": 2, "lock": False,
        "slug": "shadow-empress-m16a4"
    },
    {
        "name": "Shrine Keeper - M16A4",
        "weapon_type": "M16A4",
        "skin_name": "Shrine Keeper",
        "rarity": "classified",
        "value": Decimal("850.00"),
        "img_key": "im5", "row": 2, "col": 5, "lock": False,
        "slug": "shrine-keeper-m16a4"
    },
    {
        "name": "Radiant Nebula - Mini14",
        "weapon_type": "Mini14",
        "skin_name": "Radiant Nebula",
        "rarity": "classified",
        "value": Decimal("820.00"),
        "img_key": "im4", "row": 1, "col": 3, "lock": False,
        "slug": "radiant-nebula-mini14"
    },
    {
        "name": "Cloudbuster - UMP45",
        "weapon_type": "UMP45",
        "skin_name": "Cloudbuster",
        "rarity": "classified",
        "value": Decimal("800.00"),
        "img_key": "im5", "row": 2, "col": 2, "lock": False,
        "slug": "cloudbuster-ump45"
    },
    {
        "name": "Rhino Terror - Vector",
        "weapon_type": "Vector",
        "skin_name": "Rhino Terror",
        "rarity": "classified",
        "value": Decimal("780.00"),
        "img_key": "im1", "row": 3, "col": 1, "lock": False,
        "slug": "rhino-terror-vector"
    },
    {
        "name": "Cherry Blossom - S12K",
        "weapon_type": "S12K",
        "skin_name": "Cherry Blossom",
        "rarity": "classified",
        "value": Decimal("750.00"),
        "img_key": "im4", "row": 1, "col": 4, "lock": False,
        "slug": "cherry-blossom-s12k"
    },
    {
        "name": "Golden Midnight - S1897",
        "weapon_type": "S1897",
        "skin_name": "Golden Midnight",
        "rarity": "classified",
        "value": Decimal("720.00"),
        "img_key": "im5", "row": 2, "col": 3, "lock": False,
        "slug": "golden-midnight-s1897"
    },
    {
        "name": "Masked Psychic - M16A4",
        "weapon_type": "M16A4",
        "skin_name": "Masked Psychic",
        "rarity": "classified",
        "value": Decimal("700.00"),
        "img_key": "im5", "row": 3, "col": 2, "lock": False,
        "slug": "masked-psychic-m16a4"
    },
    {
        "name": "SKS (Steel Front)",
        "weapon_type": "SKS",
        "skin_name": "Steel Front",
        "rarity": "classified",
        "value": Decimal("680.00"),
        "img_key": "im2", "row": 3, "col": 5, "lock": True,
        "slug": "sks-steel-front"
    },
    {
        "name": "M24 (Refined)",
        "weapon_type": "M24",
        "skin_name": "Refined",
        "rarity": "restricted",
        "value": Decimal("650.00"),
        "img_key": "im4", "row": 3, "col": 4, "lock": True,
        "slug": "m24-refined"
    },
    {
        "name": "Red - Helmet",
        "weapon_type": "Helmet",
        "skin_name": "Red",
        "rarity": "classified",
        "value": Decimal("620.00"),
        "img_key": "im5", "row": 3, "col": 3, "lock": False,
        "slug": "red-helmet"
    },
    {
        "name": "Night Maiden Helmet",
        "weapon_type": "Helmet",
        "skin_name": "Night Maiden",
        "rarity": "classified",
        "value": Decimal("600.00"),
        "img_key": "im4", "row": 1, "col": 5, "lock": False,
        "slug": "night-maiden-helmet"
    },
    {
        "name": "Rippling Charm Helmet",
        "weapon_type": "Helmet",
        "skin_name": "Rippling Charm",
        "rarity": "classified",
        "value": Decimal("580.00"),
        "img_key": "im2", "row": 3, "col": 3, "lock": False,
        "slug": "rippling-charm-helmet"
    },
    {
        "name": "Neon Vixen Mask",
        "weapon_type": "Clothes",
        "skin_name": "Neon Vixen",
        "rarity": "classified",
        "value": Decimal("550.00"),
        "img_key": "im1", "row": 2, "col": 5, "lock": False,
        "slug": "neon-vixen-mask"
    },
    {
        "name": "Cybernetic Trance Cover",
        "weapon_type": "Clothes",
        "skin_name": "Cybernetic Trance",
        "rarity": "classified",
        "value": Decimal("520.00"),
        "img_key": "im3", "row": 2, "col": 5, "lock": False,
        "slug": "cybernetic-trance-cover"
    },
    {
        "name": "Poseidon's Ironguard Cover",
        "weapon_type": "Clothes",
        "skin_name": "Poseidon's Ironguard",
        "rarity": "classified",
        "value": Decimal("500.00"),
        "img_key": "im1", "row": 3, "col": 2, "lock": False,
        "slug": "poseidons-ironguard-cover"
    },
    {
        "name": "Star Guardian Headpiece",
        "weapon_type": "Clothes",
        "skin_name": "Star Guardian",
        "rarity": "classified",
        "value": Decimal("480.00"),
        "img_key": "im1", "row": 3, "col": 3, "lock": False,
        "slug": "star-guardian-headpiece"
    },
    {
        "name": "Bio Scout Set",
        "weapon_type": "Clothes",
        "skin_name": "Bio Scout",
        "rarity": "classified",
        "value": Decimal("460.00"),
        "img_key": "im2", "row": 3, "col": 4, "lock": False,
        "slug": "bio-scout-set"
    },
    {
        "name": "Wasteland Samurai Set",
        "weapon_type": "Clothes",
        "skin_name": "Wasteland Samurai",
        "rarity": "classified",
        "value": Decimal("440.00"),
        "img_key": "im3", "row": 3, "col": 0, "lock": False,
        "slug": "wasteland-samurai-set"
    },
    {
        "name": "Rosy Secret - Pan",
        "weapon_type": "Pan",
        "skin_name": "Rosy Secret",
        "rarity": "classified",
        "value": Decimal("420.00"),
        "img_key": "im5", "row": 2, "col": 1, "lock": False,
        "slug": "rosy-secret-pan"
    },
    {
        "name": "Angry Red - Pan",
        "weapon_type": "Pan",
        "skin_name": "Angry Red",
        "rarity": "classified",
        "value": Decimal("400.00"),
        "img_key": "im5", "row": 3, "col": 1, "lock": False,
        "slug": "angry-red-pan"
    },

    # Restricted & Tactical Items & Backpacks (200 - 380 UC)
    {
        "name": "Painkiller #11 - Pan",
        "weapon_type": "Pan",
        "skin_name": "Painkiller #11",
        "rarity": "restricted",
        "value": Decimal("380.00"),
        "img_key": "im4", "row": 2, "col": 2, "lock": False,
        "slug": "painkiller-11-pan"
    },
    {
        "name": "Squeaktology Set",
        "weapon_type": "Clothes",
        "skin_name": "Squeaktology",
        "rarity": "restricted",
        "value": Decimal("360.00"),
        "img_key": "im4", "row": 2, "col": 0, "lock": False,
        "slug": "squeaktology-set"
    },
    {
        "name": "Frosty Geek Set",
        "weapon_type": "Clothes",
        "skin_name": "Frosty Geek",
        "rarity": "restricted",
        "value": Decimal("340.00"),
        "img_key": "im4", "row": 2, "col": 1, "lock": False,
        "slug": "frosty-geek-set"
    },
    {
        "name": "Wonderland Traveler Set",
        "weapon_type": "Clothes",
        "skin_name": "Wonderland Traveler",
        "rarity": "restricted",
        "value": Decimal("320.00"),
        "img_key": "im4", "row": 2, "col": 3, "lock": False,
        "slug": "wonderland-traveler-set"
    },
    {
        "name": "Captain Lionheart Headpiece",
        "weapon_type": "Clothes",
        "skin_name": "Captain Lionheart",
        "rarity": "restricted",
        "value": Decimal("300.00"),
        "img_key": "im4", "row": 2, "col": 4, "lock": False,
        "slug": "captain-lionheart-headpiece"
    },
    {
        "name": "Son Goku Helmet",
        "weapon_type": "Helmet",
        "skin_name": "Son Goku",
        "rarity": "restricted",
        "value": Decimal("290.00"),
        "img_key": "im4", "row": 2, "col": 5, "lock": False,
        "slug": "son-goku-helmet"
    },
    {
        "name": "Futuristic Streetwear Backpack",
        "weapon_type": "Backpack",
        "skin_name": "Futuristic Streetwear",
        "rarity": "restricted",
        "value": Decimal("280.00"),
        "img_key": "im4", "row": 3, "col": 0, "lock": False,
        "slug": "futuristic-streetwear-backpack"
    },
    {
        "name": "Angry King Pig Backpack",
        "weapon_type": "Backpack",
        "skin_name": "Angry King Pig",
        "rarity": "restricted",
        "value": Decimal("260.00"),
        "img_key": "im4", "row": 3, "col": 1, "lock": False,
        "slug": "angry-king-pig-backpack"
    },
    {
        "name": "Black Cat Backpack",
        "weapon_type": "Backpack",
        "skin_name": "Black Cat",
        "rarity": "restricted",
        "value": Decimal("250.00"),
        "img_key": "im4", "row": 3, "col": 2, "lock": False,
        "slug": "black-cat-backpack"
    },
    {
        "name": "Sweets Treats Backpack",
        "weapon_type": "Backpack",
        "skin_name": "Sweets Treats",
        "rarity": "restricted",
        "value": Decimal("240.00"),
        "img_key": "im4", "row": 3, "col": 3, "lock": False,
        "slug": "sweets-treats-backpack"
    },
    {
        "name": "Vest (Cobra) (Lv. 4)",
        "weapon_type": "Armor",
        "skin_name": "Vest (Cobra) (Lv. 4)",
        "rarity": "restricted",
        "value": Decimal("230.00"),
        "img_key": "im3", "row": 3, "col": 2, "lock": False,
        "slug": "vest-cobra-lv-4"
    },
    {
        "name": "8x Scope",
        "weapon_type": "Attachment",
        "skin_name": "8x Scope",
        "rarity": "restricted",
        "value": Decimal("210.00"),
        "img_key": "im3", "row": 3, "col": 3, "lock": False,
        "slug": "8x-scope"
    },
    {
        "name": "Flash Hider (Sniper Rifles) (Refined)",
        "weapon_type": "Attachment",
        "skin_name": "Flash Hider (Sniper Rifles) (Refined)",
        "rarity": "restricted",
        "value": Decimal("200.00"),
        "img_key": "im3", "row": 3, "col": 1, "lock": False,
        "slug": "flash-hider-sniper-rifles-refined"
    },
]


def extract_and_save_item_image(card, slug, is_lock=False):
    """
    Crops item from card, pads properly with aspect ratio intact, enhances sharpness/brightness,
    applies rounded mask, and saves to media/items/ and static/items/.
    """
    c = card.copy()
    if is_lock:
        c[0:22, 0:75] = c[24, 10]

    # Artwork region in card: y: 7..58, x: 15..135
    roi = c[7:58, 15:135]

    # Estimate linear gradient background
    bg_left = np.mean(roi[:, :5], axis=(0, 1))
    bg_right = np.mean(roi[:, -5:], axis=(0, 1))
    bg_grad = np.zeros_like(roi, dtype=np.float32)
    for col in range(roi.shape[1]):
        alpha = col / max(1, roi.shape[1] - 1)
        bg_grad[:, col] = (1 - alpha) * bg_left + alpha * bg_right

    diff = np.linalg.norm(roi.astype(np.float32) - bg_grad, axis=2)
    mask = diff > 16
    mask[:2, :] = False

    coords = np.argwhere(mask)
    if len(coords) >= 40:
        y_min, x_min = coords.min(axis=0)
        y_max, x_max = coords.max(axis=0)
        y1 = max(7, 7 + y_min - 3)
        y2 = min(58, 7 + y_max + 3)
        x1 = max(15, 15 + x_min - 3)
        x2 = min(135, 15 + x_max + 3)
    else:
        y1, y2, x1, x2 = 7, 58, 30, 120

    cropped_art = c[y1:y2, x1:x2]
    pil_art = Image.fromarray(cv2.cvtColor(cropped_art, cv2.COLOR_BGR2RGB))

    # Pad to square to maintain proportions
    w, h = pil_art.size
    side = max(w, h, 60)
    bg_sample = tuple(pil_art.getpixel((0, 0)))
    sq_art = Image.new('RGB', (side, side), bg_sample)
    sq_art.paste(pil_art, ((side - w) // 2, (side - h) // 2))

    # Enhance
    sq_art = ImageEnhance.Brightness(sq_art).enhance(1.20)
    sq_art = ImageEnhance.Contrast(sq_art).enhance(1.20)

    scaled = sq_art.resize((240, 240), Image.Resampling.LANCZOS)
    scaled = ImageEnhance.Sharpness(scaled).enhance(1.25)

    mask_shape = Image.new('L', (240, 240), 0)
    draw = ImageDraw.Draw(mask_shape)
    draw.rounded_rectangle([(0, 0), (240, 240)], radius=24, fill=255)
    mask_shape = mask_shape.filter(ImageFilter.GaussianBlur(radius=0.75))

    canvas = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
    canvas.paste(scaled, (8, 8), mask_shape)

    # Save destinations
    media_dir = Path(settings.MEDIA_ROOT) / 'items'
    media_dir.mkdir(parents=True, exist_ok=True)
    static_dir = Path(settings.BASE_DIR) / 'static' / 'items'
    static_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{slug}.png"
    canvas.save(media_dir / filename, "PNG")
    canvas.save(static_dir / filename, "PNG")
    return f"items/{filename}"


def main():
    print("=" * 60)
    print("ADDING STANDALONE ITEMS (WITHOUT CASE)")
    print("=" * 60)

    # Load source images
    loaded_images = {}
    for key, info in IMAGES_LAYOUT.items():
        img_path = UPLOADED_DIR / info['file']
        if not img_path.exists():
            raise FileNotFoundError(f"Missing source image: {img_path}")
        loaded_images[key] = cv2.imread(str(img_path))
        print(f"Loaded {key}: {info['file']}")

    added_count = 0
    updated_count = 0

    values_list = []

    for item_data in NEW_ITEMS_DATA:
        key = item_data['img_key']
        r = item_data['row']
        c = item_data['col']
        lock = item_data.get('lock', False)
        slug = item_data['slug']

        img = loaded_images[key]
        y1 = IMAGES_LAYOUT[key]['row_ys'][r]
        y2 = min(img.shape[0], y1 + 81)
        x1, x2 = COLS_BOUNDS[c]
        card = img[y1:y2, x1:x2]

        rel_img_path = extract_and_save_item_image(card, slug, is_lock=lock)

        val = item_data['value']
        values_list.append(val)

        rarity = item_data['rarity']
        color = RARITY_COLORS.get(rarity, '#4b69ff')

        item_obj, created = Item.objects.update_or_create(
            name=item_data['name'],
            defaults={
                'weapon_type': item_data['weapon_type'],
                'skin_name': item_data['skin_name'],
                'rarity': rarity,
                'rarity_color': color,
                'value': val,
                'image': rel_img_path,
                'image_url': f"/media/{rel_img_path}",
            }
        )

        if created:
            added_count += 1
            status = "CREATED"
        else:
            updated_count += 1
            status = "UPDATED"

        print(f"[{status}] {item_obj.name:<36} | {item_obj.rarity:<10} | {item_obj.value:>8} UC | img: {rel_img_path}")

    print("=" * 60)
    print(f"Total processed: {len(NEW_ITEMS_DATA)}")
    print(f"Created: {added_count}, Updated: {updated_count}")
    print(f"Min price: {min(values_list)} UC, Max price: {max(values_list)} UC")
    print(f"Total items in DB now: {Item.objects.count()}")
    print("=" * 60)


if __name__ == '__main__':
    main()
