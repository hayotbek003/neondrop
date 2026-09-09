from decimal import Decimal
from django.core.management.base import BaseCommand
from cases.models import Item
from scripts.add_standalone_items import NEW_ITEMS_DATA, RARITY_COLORS


class Command(BaseCommand):
    help = "Imports standalone items from the 5 uploaded screenshot grids (prices 200 to 13,694 UC) without creating a case."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Importing standalone items into database..."))
        added = 0
        updated = 0

        for item_data in NEW_ITEMS_DATA:
            name = item_data['name']
            val = item_data['value']
            rarity = item_data['rarity']
            color = RARITY_COLORS.get(rarity, '#4b69ff')
            slug = item_data['slug']
            rel_img_path = f"items/{slug}.png"

            item_obj, created = Item.objects.update_or_create(
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
            if created:
                added += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"Successfully finished: {added} created, {updated} updated. Total items in DB: {Item.objects.count()}"
        ))
