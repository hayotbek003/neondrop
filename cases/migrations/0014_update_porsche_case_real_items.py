# Generated for NEONDROP: Update Porsche 911 GT3 RS case with real items, images, prices and 80% RTP
from decimal import Decimal
from django.db import migrations

PORSCHE_ITEMS = [
    {
        'name': 'Porsche 911 GT3 RS',
        'weapon_type': 'Vehicle',
        'skin_name': '911 GT3 RS',
        'rarity': 'knife',
        'rarity_color': '#ffd700',
        'value': Decimal('45000.00'),
        'chance_percent': 5.314,
        'image': 'items/porsche-911-gt3-rs.png'
    },
    {
        'name': 'Bugatti La Voiture Noire (Warrior)',
        'weapon_type': 'Vehicle',
        'skin_name': 'La Voiture Noire (Warrior)',
        'rarity': 'covert',
        'rarity_color': '#eb4b4b',
        'value': Decimal('30000.00'),
        'chance_percent': 6.211,
        'image': 'items/bugatti-la-voiture-noire-warrior.png'
    },
    {
        'name': 'Koenigsegg Jesko (Dawn)',
        'weapon_type': 'Vehicle',
        'skin_name': 'Jesko (Dawn)',
        'rarity': 'covert',
        'rarity_color': '#eb4b4b',
        'value': Decimal('25000.00'),
        'chance_percent': 6.542,
        'image': 'items/koenigsegg-jesko-dawn.png'
    },
    {
        'name': 'Koenigsegg One:1 Phoenix',
        'weapon_type': 'Vehicle',
        'skin_name': 'One:1 Phoenix',
        'rarity': 'covert',
        'rarity_color': '#eb4b4b',
        'value': Decimal('22000.00'),
        'chance_percent': 6.749,
        'image': 'items/koenigsegg-one-1-phoenix.png'
    },
    {
        'name': 'Lamborghini Aventador SVJ Blue',
        'weapon_type': 'Vehicle',
        'skin_name': 'Aventador SVJ Blue',
        'rarity': 'covert',
        'rarity_color': '#eb4b4b',
        'value': Decimal('20000.00'),
        'chance_percent': 6.891,
        'image': 'items/lamborghini-aventador-svj-blue.png'
    },
    {
        'name': 'Koenigsegg Gemera (Rainbow)',
        'weapon_type': 'Vehicle',
        'skin_name': 'Gemera (Rainbow)',
        'rarity': 'covert',
        'rarity_color': '#eb4b4b',
        'value': Decimal('18000.00'),
        'chance_percent': 7.035,
        'image': 'items/koenigsegg-gemera-rainbow.png'
    },
    {
        'name': 'Lamborghini Estoque Oro',
        'weapon_type': 'Vehicle',
        'skin_name': 'Estoque Oro',
        'rarity': 'covert',
        'rarity_color': '#eb4b4b',
        'value': Decimal('15000.00'),
        'chance_percent': 7.258,
        'image': 'items/lamborghini-estoque-oro.png'
    },
    {
        'name': 'Bentley Flying Spur Mulliner',
        'weapon_type': 'Vehicle',
        'skin_name': 'Flying Spur Mulliner',
        'rarity': 'covert',
        'rarity_color': '#eb4b4b',
        'value': Decimal('13694.00'),
        'chance_percent': 7.357,
        'image': 'items/bentley-flying-spur-mulliner.png'
    },
    {
        'name': 'Bugatti Veyron 16.4 (Gold)',
        'weapon_type': 'Vehicle',
        'skin_name': 'Veyron 16.4 (Gold)',
        'rarity': 'covert',
        'rarity_color': '#eb4b4b',
        'value': Decimal('13200.00'),
        'chance_percent': 7.395,
        'image': 'items/bugatti-veyron-16-4-gold.png'
    },
    {
        'name': 'Aston Martin Valkyrie (Racing Green)',
        'weapon_type': 'Vehicle',
        'skin_name': 'Valkyrie (Racing Green)',
        'rarity': 'covert',
        'rarity_color': '#eb4b4b',
        'value': Decimal('11500.00'),
        'chance_percent': 7.527,
        'image': 'items/aston-martin-valkyrie-racing-green.png'
    },
    {
        'name': 'Tesla Cybertruck (Dystopia Blue)',
        'weapon_type': 'Vehicle',
        'skin_name': 'Cybertruck (Dystopia Blue)',
        'rarity': 'covert',
        'rarity_color': '#eb4b4b',
        'value': Decimal('9800.00'),
        'chance_percent': 7.661,
        'image': 'items/tesla-cybertruck-dystopia-blue.png'
    },
    {
        'name': 'Serene Lumina Dacia',
        'weapon_type': 'Vehicle',
        'skin_name': 'Lumina Dacia',
        'rarity': 'covert',
        'rarity_color': '#eb4b4b',
        'value': Decimal('7800.00'),
        'chance_percent': 7.822,
        'image': 'items/serene-lumina-dacia.png'
    },
    {
        'name': 'Enchanted Carpet Glider',
        'weapon_type': 'Vehicle',
        'skin_name': 'Carpet Glider',
        'rarity': 'classified',
        'rarity_color': '#d32ce6',
        'value': Decimal('4400.00'),
        'chance_percent': 8.073,
        'image': 'items/enchanted-carpet-glider.png'
    },
    {
        'name': 'Myriad Prism Glider',
        'weapon_type': 'Vehicle',
        'skin_name': 'Prism Glider',
        'rarity': 'classified',
        'rarity_color': '#d32ce6',
        'value': Decimal('4000.00'),
        'chance_percent': 8.165,
        'image': 'items/myriad-prism-glider.png'
    },
]


def update_porsche_case(apps, schema_editor):
    Case = apps.get_model('cases', 'Case')
    Item = apps.get_model('cases', 'Item')
    CaseItem = apps.get_model('cases', 'CaseItem')

    case = Case.objects.filter(slug='porsche-911-gt3-rs').first()
    if not case:
        case = Case.objects.filter(name__iexact='Porsche 911 GT3 RS').first()

    if not case:
        return

    # Ensure case properties
    case.name = 'Porsche 911 GT3 RS'
    case.price = Decimal('20000.00')
    case.active = True
    case.is_popular = True
    case.is_new = True
    case.color_theme = 'godlike-gold'
    case.image = 'cases/porsche-911-gt3-rs.jpg'
    case.save()

    # Create or update each of the 14 real items
    item_objs = []
    for it_data in PORSCHE_ITEMS:
        item = Item.objects.filter(name=it_data['name']).first()
        if not item:
            item = Item.objects.create(
                name=it_data['name'],
                weapon_type=it_data['weapon_type'],
                skin_name=it_data['skin_name'],
                rarity=it_data['rarity'],
                rarity_color=it_data['rarity_color'],
                value=it_data['value'],
                image=it_data['image'],
                game='PUBG'
            )
        else:
            update_fields = []
            if item.name in ('Porsche 911 GT3 RS', 'Myriad Prism Glider'):
                item.value = it_data['value']
                update_fields.append('value')
            if not item.image or 'placeholder' in str(item.image) or item.name == 'Porsche 911 GT3 RS':
                item.image = it_data['image']
                update_fields.append('image')
            if update_fields:
                item.save(update_fields=list(set(update_fields)))

        item_objs.append((item, it_data['chance_percent']))

    # Remove old placeholder CaseItem relations for this case
    CaseItem.objects.filter(case=case).delete()

    # Re-create clean CaseItem relations with exact 80% RTP weights
    new_case_items = []
    for item, weight in item_objs:
        new_case_items.append(
            CaseItem(
                case=case,
                item=item,
                weight=weight
            )
        )
    CaseItem.objects.bulk_create(new_case_items)

    # Clean up obsolete placeholder items that start with 'Porsche 911 GT3 RS — Item'
    Item.objects.filter(name__startswith='Porsche 911 GT3 RS — Item').delete()


def reverse_func(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cases', '0013_import_supercars_cases'),
    ]

    operations = [
        migrations.RunPython(update_porsche_case, reverse_func),
    ]
