# Generated for NEONDROP production data synchronization
import json
from pathlib import Path
from decimal import Decimal
from django.db import migrations
from django.conf import settings
from django.utils.text import slugify


def import_supercars_cases(apps, schema_editor):
    Case = apps.get_model('cases', 'Case')
    Item = apps.get_model('cases', 'Item')
    CaseItem = apps.get_model('cases', 'CaseItem')
    Category = apps.get_model('cases', 'Category')

    json_path = Path(settings.BASE_DIR) / 'cases' / 'resources' / 'supercars_cases.json'
    if not json_path.exists():
        return

    try:
        cases_data = json.loads(json_path.read_text(encoding='utf-8'))
    except Exception:
        return

    expensive_cat, _ = Category.objects.get_or_create(
        slug='expensive',
        defaults={'name': 'Дорогие кейсы', 'order': 4}
    )

    theme_map = {
        'porsche-911-gt3-rs': 'godlike-gold',
        'rolls-royce': 'luxury-silver',
        'mclaren': 'demon-orange',
        'ferrari': 'supreme-red',
        'bugatti': 'cyber-pink',
        'cars-supercars': 'frost-cyan',
    }

    rarity_map = {
        'common': 'common',
        'uncommon': 'uncommon',
        'rare': 'rare',
        'epic': 'epic',
        'legendary': 'legendary',
        'mythic': 'mythic',
        'knife': 'knife',
        'covert': 'covert',
        'classified': 'classified',
        'restricted': 'restricted',
        'mil-spec': 'mil-spec',
    }

    for case_idx, c_dict in enumerate(cases_data, 1):
        raw_name = c_dict['name']
        case_price = Decimal(str(c_dict.get('price_uc', 0)))
        case_slug = slugify(raw_name)
        case_theme = theme_map.get(case_slug, 'cyber-pink')

        case_obj = Case.objects.filter(slug=case_slug).first()
        if not case_obj:
            case_obj = Case.objects.filter(name__iexact=raw_name).first()

        if not case_obj:
            case_obj = Case.objects.create(
                name=raw_name,
                slug=case_slug,
                price=case_price,
                category=expensive_cat,
                color_theme=case_theme,
                active=True,
                is_new=True,
                is_popular=True,
                order=100 + case_idx,
                image=f'cases/{case_slug}.jpg'
            )
        else:
            case_obj.name = raw_name
            case_obj.price = case_price
            case_obj.category = expensive_cat
            case_obj.color_theme = case_theme
            case_obj.active = True
            case_obj.is_new = True
            case_obj.is_popular = True
            if not case_obj.image:
                case_obj.image = f'cases/{case_slug}.jpg'
            case_obj.save()

        items_list = c_dict.get('items', [])
        for item_idx, it_dict in enumerate(items_list, 1):
            raw_item_name = it_dict['name']
            item_price = Decimal(str(it_dict.get('price_uc', 0)))
            raw_rarity = str(it_dict.get('rarity', 'common')).lower().strip()
            item_rarity = rarity_map.get(raw_rarity, 'common')
            weight = float(it_dict.get('chance_percent', 0.0))

            item_obj = Item.objects.filter(name=raw_item_name).first()
            if not item_obj:
                item_obj = Item.objects.create(
                    name=raw_item_name,
                    value=item_price,
                    rarity=item_rarity,
                    game='PUBG',
                    image=f'items/{case_slug}_item_{item_idx:02d}.webp'
                )

            ci = CaseItem.objects.filter(case=case_obj, item=item_obj).first()
            if not ci:
                CaseItem.objects.create(
                    case=case_obj,
                    item=item_obj,
                    weight=weight
                )
            else:
                if ci.weight != weight:
                    ci.weight = weight
                    ci.save(update_fields=['weight'])


def reverse_import(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cases', '0012_pubgimportsession'),
    ]

    operations = [
        migrations.RunPython(import_supercars_cases, reverse_import),
    ]
