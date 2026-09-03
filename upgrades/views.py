import logging
import secrets
from decimal import Decimal
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.db import transaction
from django.utils import timezone

from .models import UpgradeAttempt
from cases.models import Item
from inventory.models import InventoryItem
from cases.provably_fair import generate_server_seed, calculate_provably_fair_roll, hash_seed
from payments.services import modify_user_balance
from config.security import rate_limit, get_client_ip

security_logger = logging.getLogger('neondrop.security')
audit_logger = logging.getLogger('neondrop.audit')

@login_required
def index_view(request):
    inventory_items = InventoryItem.objects.filter(user=request.user, is_sold=False).select_related('item').order_by('-item__value')
    target_items = Item.objects.all().order_by('value')
    
    context = {
        'inventory_items': inventory_items,
        'target_items': target_items,
        'active_tab': 'upgrade',
    }
    return render(request, 'upgrade.html', context)

upgrade_view = index_view

@rate_limit(key_prefix='upgrade_calc', limit=60, period=60, by_user=True)
@login_required
def calculate_chance_api(request):
    input_inv_id = request.GET.get('input_id') or request.GET.get('inventory_item_id')
    target_item_id = request.GET.get('target_id') or request.GET.get('target_item_id')
    
    if not input_inv_id or not target_item_id:
        return JsonResponse({'success': False, 'error': 'Необходимо выбрать исходный и целевой скин.'}, status=400)
        
    try:
        inv_item = InventoryItem.objects.get(id=input_inv_id, user=request.user, is_sold=False)
        target_item = Item.objects.get(id=target_item_id)
    except (InventoryItem.DoesNotExist, Item.DoesNotExist):
        return JsonResponse({'success': False, 'error': 'Выбранные предметы недоступны.'}, status=400)
        
    if target_item.value <= inv_item.item.value:
        return JsonResponse({'success': False, 'error': 'Целевой скин должен быть дороже исходного.'}, status=400)
        
    chance = float(inv_item.item.value / target_item.value) * 0.95
    chance = min(0.80, max(0.01, chance))
    chance_percent = round(chance * 100.0, 2)
    
    return JsonResponse({
        'success': True,
        'chance_percent': chance_percent,
        'input_val': float(inv_item.item.value),
        'target_val': float(target_item.value),
    })

@rate_limit(key_prefix='upgrade_exec', limit=20, period=60, by_user=True)
@login_required
@require_POST
@transaction.atomic
def execute_upgrade_api(request):
    ip = get_client_ip(request)
    input_inv_id = request.POST.get('input_id') or request.POST.get('inventory_item_id')
    target_item_id = request.POST.get('target_id') or request.POST.get('target_item_id')
    client_seed = request.POST.get('client_seed') or secrets.token_hex(16)
    client_seed = ''.join(c for c in client_seed if c.isalnum())[:64] or secrets.token_hex(16)
    
    # 1. Lock and validate source inventory item
    try:
        inv_item = InventoryItem.objects.select_for_update().get(id=input_inv_id, user=request.user, is_sold=False)
        target_item = Item.objects.get(id=target_item_id)
    except InventoryItem.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Исходный скин не найден в вашем инвентаре.'}, status=400)
    except Item.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Целевой скин не найден.'}, status=400)
        
    if target_item.value <= inv_item.item.value:
        return JsonResponse({'success': False, 'error': 'Целевой скин должен быть дороже исходного.'}, status=400)
        
    # 2. Server-side probability calculation
    chance = float(inv_item.item.value / target_item.value) * 0.95
    chance = min(0.80, max(0.01, chance))
    
    # 3. Provably Fair Roll
    server_seed = generate_server_seed()
    server_seed_hash = hash_seed(server_seed)
    nonce = request.user.profile.total_opened + 1
    roll_float = calculate_provably_fair_roll(server_seed, client_seed, nonce)
    
    is_win = roll_float <= chance
    
    # 4. Burn input item
    inv_item.is_sold = True
    inv_item.sold_price = Decimal('0.00')
    inv_item.sold_at = timezone.now()
    inv_item.save(update_fields=['is_sold', 'sold_price', 'sold_at'])
    
    won_inv_item = None
    if is_win:
        won_inv_item = InventoryItem.objects.create(
            user=request.user,
            item=target_item,
            source='upgrade'
        )
        # Update winnings
        request.user.profile.total_winnings += target_item.value
        request.user.profile.save(update_fields=['total_winnings'])
        
    # 5. Record Upgrade Attempt
    attempt = UpgradeAttempt.objects.create(
        user=request.user,
        source_item=inv_item.item,
        target_item=target_item,
        chance=round(chance * 100.0, 2),
        roll=round(roll_float * 100.0, 4),
        is_success=is_win,
        server_seed=server_seed
    )

    audit_logger.info(
        f"UPGRADE_ATTEMPT: user={request.user.username} (id={request.user.id}) | "
        f"input={inv_item.item.name} (${inv_item.item.value}) -> target={target_item.name} (${target_item.value}) | "
        f"chance={chance*100:.2f}% | roll={roll_float*100:.4f}% | win={is_win} | ip={ip}"
    )
    
    target_degree = int(roll_float * 360.0)
    
    target_item_dict = {
        'id': target_item.id,
        'name': target_item.name,
        'value': float(target_item.value),
        'image_url': target_item.image_url or (target_item.image.url if target_item.image else ''),
        'rarity_color': target_item.rarity_color,
    }
    
    return JsonResponse({
        'success': True,
        'is_win': is_win,
        'is_won': is_win,
        'chance': round(chance * 100.0, 2),
        'chance_percent': round(chance * 100.0, 2),
        'roll': round(roll_float * 100.0, 4),
        'roll_percent': round(roll_float * 100.0, 4),
        'target_deg': target_degree,
        'target_degree': target_degree,
        'won_item': target_item_dict if is_win else None,
        'target_item': target_item_dict,
        'server_seed_hash': server_seed_hash,
        'server_seed': server_seed,
        'client_seed': client_seed,
        'nonce': nonce,
    })
