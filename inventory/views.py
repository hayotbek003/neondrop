import logging
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.http import JsonResponse
from django.db import transaction
from django.utils import timezone

from .models import InventoryItem
from payments.services import modify_user_balance
from config.security import rate_limit, get_client_ip

security_logger = logging.getLogger('neondrop.security')
audit_logger = logging.getLogger('neondrop.audit')

@login_required
def inventory_view(request):
    items = InventoryItem.objects.filter(user=request.user, is_sold=False).select_related('item').order_by('-created_at')
    total_value = sum((inv.item.value for inv in items), Decimal('0.00'))
    total_count = items.count()
    
    context = {
        'items': items,
        'total_value': total_value,
        'total_count': total_count,
        'active_tab': 'inventory',
    }
    return render(request, 'inventory.html', context)

# Alias for backwards compatibility
index_view = inventory_view

@rate_limit(key_prefix='inv_list', limit=60, period=60, by_user=True)
@login_required
@require_GET
def api_inventory_list(request):
    items = InventoryItem.objects.filter(user=request.user, is_sold=False).select_related('item').order_by('-created_at')
    data = []
    for inv in items:
        data.append({
            'id': inv.id,
            'item_id': inv.item.id,
            'name': inv.item.name,
            'weapon_type': inv.item.weapon_type,
            'skin_name': inv.item.skin_name,
            'value': float(inv.item.value),
            'rarity': inv.item.rarity,
            'rarity_name': inv.item.rarity_display_ru,
            'rarity_color': inv.item.rarity_color,
            'image_url': inv.item.image_url or (inv.item.image.url if inv.item.image else ''),
        })
    return JsonResponse({'success': True, 'items': data})

@rate_limit(key_prefix='sell_item', limit=30, period=60, by_user=True)
@login_required
@require_POST
@transaction.atomic
def sell_item_api(request, item_id):
    ip = get_client_ip(request)
    
    # 1. Lock item and verify ownership
    try:
        inv_item = InventoryItem.objects.select_for_update().get(id=item_id, user=request.user, is_sold=False)
    except InventoryItem.DoesNotExist:
        security_logger.warning(
            f"Unauthorized or invalid item sell attempt: user={request.user.username} (id={request.user.id}), "
            f"item_id={item_id}, ip={ip}"
        )
        return JsonResponse({'success': False, 'error': 'Предмет не найден или уже был продан.'}, status=400)

    item_val = inv_item.item.value
    
    # 2. Credit user balance atomically
    ledger_tx = modify_user_balance(
        user=request.user,
        amount_delta=item_val,
        transaction_type='item_sell',
        reference_id=f"inv:{inv_item.id}",
        description=f"Продажа скина {inv_item.item.name} (${item_val:.2f})",
        ip_address=ip
    )

    # 3. Update inventory item status
    inv_item.is_sold = True
    inv_item.sold_price = item_val
    inv_item.sold_at = timezone.now()
    inv_item.save(update_fields=['is_sold', 'sold_price', 'sold_at'])

    audit_logger.info(
        f"ITEM_SELL_SUCCESS: user={request.user.username} (id={request.user.id}) | "
        f"item={inv_item.item.name} | sold_for=${item_val} | tx_id={ledger_tx.id}"
    )

    return JsonResponse({
        'success': True,
        'sold_price': float(item_val),
        'new_balance': float(ledger_tx.balance_after),
    })

@rate_limit(key_prefix='sell_all', limit=10, period=60, by_user=True)
@login_required
@require_POST
@transaction.atomic
def sell_all_api(request):
    ip = get_client_ip(request)
    
    # Lock all unsold items belonging to user
    items = list(InventoryItem.objects.select_for_update().filter(user=request.user, is_sold=False).select_related('item'))
    
    if not items:
        return JsonResponse({'success': False, 'error': 'В инвентаре нет доступных для продажи предметов.'}, status=400)

    total_credit = sum((inv.item.value for inv in items), Decimal('0.00'))
    now = timezone.now()
    
    # Credit balance in one atomic transaction ledger
    ledger_tx = modify_user_balance(
        user=request.user,
        amount_delta=total_credit,
        transaction_type='sell_all',
        reference_id=f"bulk_sell:{len(items)}_items",
        description=f"Массовая продажа {len(items)} скинов на сумму ${total_credit:.2f}",
        ip_address=ip
    )

    # Mark all items as sold
    for inv in items:
        inv.is_sold = True
        inv.sold_price = inv.item.value
        inv.sold_at = now
        inv.save(update_fields=['is_sold', 'sold_price', 'sold_at'])

    audit_logger.info(
        f"BULK_SELL_SUCCESS: user={request.user.username} (id={request.user.id}) | "
        f"count={len(items)} | total_sold=${total_credit} | tx_id={ledger_tx.id}"
    )

    return JsonResponse({
        'success': True,
        'sold_count': len(items),
        'total_value': float(total_credit),
        'new_balance': float(ledger_tx.balance_after),
    })
