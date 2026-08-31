import logging
import secrets
import random
from decimal import Decimal
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.db import transaction
from django.utils import timezone

from .models import Contract, ContractInputItem
from cases.models import Item
from inventory.models import InventoryItem
from cases.provably_fair import generate_server_seed, calculate_provably_fair_roll, hash_seed
from config.security import rate_limit, get_client_ip

security_logger = logging.getLogger('neondrop.security')
audit_logger = logging.getLogger('neondrop.audit')

@login_required
def index_view(request):
    inventory_items = InventoryItem.objects.filter(user=request.user, is_sold=False).select_related('item').order_by('-item__value')
    context = {
        'inventory_items': inventory_items,
        'active_tab': 'contracts',
    }
    return render(request, 'contracts.html', context)

contracts_view = index_view

@rate_limit(key_prefix='contract_create', limit=15, period=60, by_user=True)
@login_required
@require_POST
@transaction.atomic
def create_contract_api(request):
    ip = get_client_ip(request)
    raw_ids = request.POST.getlist('item_ids[]') or request.POST.getlist('item_ids')
    
    # 1. Validate count constraint (3 to 10 skins)
    if not raw_ids or len(raw_ids) < 3 or len(raw_ids) > 10:
        return JsonResponse({'success': False, 'error': 'Для контракта требуется от 3 до 10 скинов.'}, status=400)
        
    try:
        item_ids = [int(i) for i in set(raw_ids)]
    except ValueError:
        return JsonResponse({'success': False, 'error': 'Некорректные идентификаторы предметов.'}, status=400)

    # 2. Lock and verify ownership of all selected items
    input_inv_items = list(InventoryItem.objects.select_for_update().filter(
        id__in=item_ids,
        user=request.user,
        is_sold=False
    ).select_related('item'))
    
    if len(input_inv_items) != len(item_ids):
        security_logger.warning(
            f"Contract craft attempt with invalid/sold items: user={request.user.username}, "
            f"requested={item_ids}, found={len(input_inv_items)}, ip={ip}"
        )
        return JsonResponse({'success': False, 'error': 'Некоторые выбранные предметы недоступны или уже были проданы.'}, status=400)

    # 3. Calculate total input value server-side
    total_input_value = sum((inv.item.value for inv in input_inv_items), Decimal('0.00'))
    min_output_value = total_input_value * Decimal('0.60')
    max_output_value = total_input_value * Decimal('3.50')
    
    # 4. Find candidate pool
    candidates = list(Item.objects.filter(active=True, value__gte=min_output_value, value__lte=max_output_value))
    if not candidates:
        candidates = list(Item.objects.filter(active=True, value__gte=min_output_value * Decimal('0.50')))
    if not candidates:
        candidates = list(Item.objects.filter(active=True))

    # 5. Provably Fair Selection
    server_seed = generate_server_seed()
    server_seed_hash = hash_seed(server_seed)
    client_seed = request.POST.get('client_seed') or secrets.token_hex(16)
    client_seed = ''.join(c for c in client_seed if c.isalnum())[:64] or secrets.token_hex(16)
    nonce = request.user.profile.total_opened + 1
    
    roll_float = calculate_provably_fair_roll(server_seed, client_seed, nonce)
    selected_index = int(roll_float * len(candidates))
    output_item = candidates[min(selected_index, len(candidates) - 1)]

    # 6. Burn all input items
    now = timezone.now()
    for inv in input_inv_items:
        inv.is_sold = True
        inv.sold_price = Decimal('0.00')
        inv.sold_at = now
        inv.save(update_fields=['is_sold', 'sold_price', 'sold_at'])

    # 7. Create crafted inventory item
    won_inv_item = InventoryItem.objects.create(
        user=request.user,
        item=output_item,
        source='contract'
    )
    
    # 8. Create Contract Record
    contract = Contract.objects.create(
        user=request.user,
        total_input_value=total_input_value,
        output_item=output_item,
        output_value=output_item.value,
        server_seed_hash=server_seed_hash,
        server_seed=server_seed,
        client_seed=client_seed,
        nonce=nonce
    )

    for inv in input_inv_items:
        ContractInputItem.objects.create(
            contract=contract,
            item=inv.item,
            value=inv.item.value
        )
        
    # Update winnings
    request.user.profile.total_winnings += output_item.value
    request.user.profile.save(update_fields=['total_winnings'])

    audit_logger.info(
        f"CONTRACT_CRAFT_SUCCESS: user={request.user.username} (id={request.user.id}) | "
        f"inputs_count={len(input_inv_items)} (total=${total_input_value}) -> output={output_item.name} (${output_item.value}) | "
        f"contract_id={contract.id} | ip={ip}"
    )

    return JsonResponse({
        'success': True,
        'output_item': {
            'id': output_item.id,
            'name': output_item.name,
            'weapon_type': output_item.weapon_type,
            'skin_name': output_item.skin_name,
            'value': float(output_item.value),
            'rarity_name': output_item.rarity_display_ru,
            'rarity_color': output_item.rarity_color,
            'image_url': output_item.image_url or (output_item.image.url if output_item.image else ''),
        },
        'total_input_value': float(total_input_value),
        'server_seed_hash': server_seed_hash,
        'server_seed': server_seed,
        'client_seed': client_seed,
        'nonce': nonce,
    })
