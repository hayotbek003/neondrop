from decimal import Decimal
from django.db import migrations


def import_standalone_items(apps, schema_editor):
    Item = apps.get_model('cases', 'Item')
    from scripts.add_standalone_items import NEW_ITEMS_DATA, RARITY_COLORS

    for item_data in NEW_ITEMS_DATA:
        name = item_data['name']
        val = item_data['value']
        rarity = item_data['rarity']
        color = RARITY_COLORS.get(rarity, '#4b69ff')
        slug = item_data['slug']
        rel_img_path = f"items/{slug}.png"

        Item.objects.update_or_create(
            name=name,
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


def rollback_standalone_items(apps, schema_editor):
    Item = apps.get_model('cases', 'Item')
    from scripts.add_standalone_items import NEW_ITEMS_DATA
    names = [d['name'] for d in NEW_ITEMS_DATA]
    Item.objects.filter(name__in=names).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('cases', '0009_setup_lamborghini_case'),
    ]

    operations = [
        migrations.RunPython(import_standalone_items, rollback_standalone_items),
    ]
