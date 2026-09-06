import logging
import secrets
import random
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import ensure_csrf_cookie
from django.http import JsonResponse
from django.db import transaction, models
from django.contrib.auth.models import User
from django.utils import timezone

from .models import (
    Case, Item, CaseItem, Opening, Category,
    PersonalCaseChance, PromoCode, PromoCodeUse, UserFreeOpening
)
from .provably_fair import (
    generate_server_seed, 
    calculate_provably_fair_roll, 
    select_weighted_item, 
    get_effective_case_chances,
    hash_seed
)
from inventory.models import InventoryItem
from users.models import Profile
from payments.models import Transaction
from payments.services import modify_user_balance, InsufficientBalanceError
from config.security import rate_limit, check_and_store_idempotency_key, get_client_ip

security_logger = logging.getLogger('neondrop.security')
audit_logger = logging.getLogger('neondrop.audit')

@ensure_csrf_cookie
def home_view(request):
    popular_cases = Case.objects.filter(active=True, is_popular=True).order_by('order', 'price')
    if not popular_cases.exists():
        popular_cases = Case.objects.filter(active=True).order_by('price')[:6]
        
    all_cases = Case.objects.filter(active=True).order_by('order', 'price')
    
    # Stats with dynamic platform offsets
    real_openings = Opening.objects.count()
    real_users = User.objects.count()
    
    stats = {
        'opened_cases': 124578482 + real_openings,
        'registered_users': 1357694 + real_users,
        'online_users': 1420 + (real_users % 180),
        'contracts': 258148 + InventoryItem.objects.filter(source='contract').count(),
    }
    
    # Top 5 winners leaderboard
    top_openings = Opening.objects.select_related('user', 'user__profile', 'item').order_by('-item__value')[:5]
    top_winners = []
    
    if top_openings.exists():
        for rank, op in enumerate(top_openings, 1):
            top_winners.append({
                'rank': rank,
                'username': op.user.username,
                'avatar': op.user.profile.display_avatar,
                'winnings': op.item.value,
                'weapon': op.item.weapon_type,
                'skin': op.item.skin_name,
                'weapon_image': op.item.image_url,
            })
    else:
        mock_data = [
            (1, 'Reed', 2543.66, 'Karambit', 'Fade', 'knife_karambit_fade'),
            (2, 'kazansik', 1830.50, 'M4A4', 'Howl', 'm4a4_howl'),
            (3, 'Shroud', 1641.32, 'AWP', 'Dragon Lore', 'awp_dragon_lore'),
            (4, 'Light', 1245.73, 'AK-47', 'Neon Rider', 'ak47_neon_rider'),
            (5, 'Fastik', 1120.21, 'Desert Eagle', 'Printstream', 'deagle_printstream'),
        ]
        for rank, uname, win, wpn, skn, img in mock_data:
            top_winners.append({
                'rank': rank,
                'username': uname,
                'avatar': f"https://api.dicebear.com/7.x/bottts/svg?seed={uname}",
                'winnings': Decimal(str(win)),
                'weapon': wpn,
                'skin': skn,
                'weapon_image': img,
            })
            
    recent_drops = Opening.objects.select_related('user', 'case', 'item').order_by('-created_at')[:15]
    
    context = {
        'popular_cases': popular_cases,
        'all_cases': all_cases,
        'stats': stats,
        'top_winners': top_winners,
        'recent_drops': recent_drops,
        'active_tab': 'home',
    }
    return render(request, 'home.html', context)

def cases_list_view(request):
    categories = Category.objects.all()
    active_category = request.GET.get('category', 'all')
    search_query = request.GET.get('q', '').strip()
    price_min = request.GET.get('min_price')
    price_max = request.GET.get('max_price')
    
    cases = Case.objects.filter(active=True)
    
    if active_category:
        cases = cases.filter(category__slug=active_category)
    if search_query:
        cases = cases.filter(name__icontains=search_query)
    if price_min:
        try:
            cases = cases.filter(price__gte=Decimal(price_min))
        except Exception:
            pass
    if price_max:
        try:
            cases = cases.filter(price__lte=Decimal(price_max))
        except Exception:
            pass
            
    cases = cases.order_by('order', 'price')
    
    context = {
        'cases': cases,
        'categories': categories,
        'active_category': active_category,
        'search_query': search_query,
        'price_min': price_min or 0,
        'price_max': price_max or 1000,
        'active_tab': 'cases',
    }
    return render(request, 'cases.html', context)

@ensure_csrf_cookie
def case_detail_view(request, slug):
    case = get_object_or_404(Case.objects.prefetch_related('case_items__item'), slug=slug, active=True)
    
    # Calculate effective item chances factoring in active personal promotion for logged-in user
    items_with_chances = get_effective_case_chances(case, request.user if request.user.is_authenticated else None)
    
    active_personal_promo = None
    free_openings_count = 0
    
    if request.user.is_authenticated:
        now = timezone.now()
        active_personal_promo = PersonalCaseChance.objects.filter(
            user=request.user,
            case=case,
            is_active=True,
            starts_at__lte=now,
            expires_at__gte=now
        ).select_related('item').first()

        user_free = UserFreeOpening.objects.filter(user=request.user, case=case).first()
        if user_free:
            free_openings_count = user_free.openings_left
        
    context = {
        'case': case,
        'items_with_chances': items_with_chances,
        'active_personal_promo': active_personal_promo,
        'free_openings_count': free_openings_count,
        'active_tab': 'cases',
    }
    return render(request, 'case_detail.html', context)

@rate_limit(key_prefix='open_case', limit=30, period=60, by_user=True)
@login_required
@require_POST
@transaction.atomic
def open_case_api(request, slug=None, case_id=None):
    ip = get_client_ip(request)
    idempotency_key = request.POST.get('idempotency_key') or request.headers.get('X-Idempotency-Key')
    
    # 1. Resolve Case
    if slug:
        case = get_object_or_404(Case, slug=slug, active=True)
    elif case_id:
        case = get_object_or_404(Case, id=case_id, active=True)
    else:
        return JsonResponse({'success': False, 'error': 'Кейс не указан.'}, status=400)

    # 2. Validate Quantity (1 to 5)
    quantity_raw = request.POST.get('quantity', 1)
    try:
        quantity = int(quantity_raw)
        if quantity not in (1, 2, 3, 4, 5):
            return JsonResponse({'success': False, 'error': 'Количество кейсов должно быть от 1 до 5.'}, status=400)
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Некорректное количество кейсов.'}, status=400)

    # 3. Idempotency protection against rapid double-clicks
    if idempotency_key:
        if not check_and_store_idempotency_key(request.user.id, idempotency_key, f"open_case_{case.id}_{quantity}"):
            return JsonResponse({
                'success': False,
                'error': 'Запрос на открытие уже обрабатывается. Пожалуйста, подождите.'
            }, status=409)

    case_items = list(case.case_items.select_related('item').all())
    if not case_items:
        return JsonResponse({'success': False, 'error': 'Кейс временно недоступен.'}, status=400)

    # 4. Check Free Openings vs Balance Deduction
    user_free = UserFreeOpening.objects.select_for_update().filter(user=request.user, case=case).first()
    available_free = user_free.openings_left if user_free else 0
    
    free_used = min(available_free, quantity)
    paid_quantity = quantity - free_used
    total_price = Decimal(str(paid_quantity)) * case.price
    
    ledger_tx = None
    if total_price > Decimal('0.00'):
        try:
            ledger_tx = modify_user_balance(
                user=request.user,
                amount_delta=-total_price,
                transaction_type='case_open',
                reference_id=f"case:{case.id}:x{quantity}",
                description=f"Открытие кейса «{case.name}» (×{paid_quantity})",
                idempotency_key=idempotency_key,
                ip_address=ip
            )
        except InsufficientBalanceError as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
        except Exception as e:
            security_logger.error(f"Balance deduction error for user {request.user.id}: {e}")
            return JsonResponse({'success': False, 'error': 'Ошибка транзакции списания средств.'}, status=500)

    # Deduct free openings
    if free_used > 0 and user_free:
        user_free.openings_left -= free_used
        user_free.save(update_fields=['openings_left', 'updated_at'])

    profile = Profile.objects.select_for_update().get(user=request.user)

    # 5. Provably Fair Item Selection for all 1..N openings
    WIN_INDEX = 50
    all_items = [ci.item for ci in case_items]
    results = []
    total_winnings = Decimal('0.00')

    base_client_seed = request.POST.get('client_seed') or secrets.token_hex(16)
    base_client_seed = ''.join(c for c in base_client_seed if c.isalnum())[:64] or secrets.token_hex(16)

    for i in range(quantity):
        server_seed = generate_server_seed()
        client_seed = f"{base_client_seed}_{i}_{secrets.token_hex(4)}"
        nonce = profile.total_opened + 1 + i

        selected_ci, roll_float, server_seed_hash = select_weighted_item(
            case_items, server_seed, client_seed, nonce, user=request.user, case=case
        )
        won_item = selected_ci.item
        total_winnings += won_item.value

        # Record Opening in Database
        opening = Opening.objects.create(
            user=request.user,
            case=case,
            item=won_item,
            price=case.price if i < paid_quantity else Decimal('0.00'),
            server_seed_hash=server_seed_hash,
            server_seed=server_seed,
            client_seed=client_seed,
            nonce=nonce
        )

        # Add Won Item to User Inventory
        inv_item = InventoryItem.objects.create(
            user=request.user,
            item=won_item,
            source='case',
            opening=opening
        )

        # Build Roulette Tape (65 items with winning item placed at fixed index 50)
        tape = []
        for t_idx in range(65):
            if t_idx == WIN_INDEX:
                tape_item = won_item
            else:
                tape_item = random.choice(all_items)
            tape.append({
                'id': tape_item.id,
                'name': tape_item.name,
                'weapon_type': tape_item.weapon_type,
                'skin_name': tape_item.skin_name,
                'value': float(tape_item.value),
                'rarity': tape_item.rarity,
                'rarity_name': tape_item.rarity_display_ru,
                'rarity_color': tape_item.rarity_color,
                'image_url': tape_item.image_url or (tape_item.image.url if tape_item.image else ''),
            })

        results.append({
            'index': i,
            'opening_id': opening.id,
            'inventory_id': inv_item.id,
            'winning_index': WIN_INDEX,
            'won_item': {
                'id': won_item.id,
                'name': won_item.name,
                'weapon_type': won_item.weapon_type,
                'skin_name': won_item.skin_name,
                'value': float(won_item.value),
                'rarity': won_item.rarity,
                'rarity_name': won_item.rarity_display_ru,
                'rarity_color': won_item.rarity_color,
                'image_url': won_item.image_url or (won_item.image.url if won_item.image else ''),
            },
            'server_seed_hash': server_seed_hash,
            'server_seed': server_seed,
            'client_seed': client_seed,
            'nonce': nonce,
            'roll_float': roll_float,
            'tape': tape,
        })

    # 6. Update Profile Statistics
    profile.total_opened += quantity
    profile.total_winnings += total_winnings
    profile.save(update_fields=['total_opened', 'total_winnings'])

    audit_logger.info(
        f"CASE_OPEN_SUCCESS: user={request.user.username} (id={request.user.id}) | "
        f"case={case.name} | qty={quantity} (paid={paid_quantity}, free={free_used}) | "
        f"cost={total_price} UC | winnings={total_winnings} UC | ip={ip}"
    )

    free_remaining = user_free.openings_left if user_free else 0

    return JsonResponse({
        'success': True,
        'quantity': quantity,
        'total_price': float(total_price),
        'paid_quantity': paid_quantity,
        'free_openings_used': free_used,
        'free_openings_remaining': free_remaining,
        'new_balance': float(profile.balance),
        'results': results,
        # Backwards compatibility for single-case response format
        'won_item': results[0]['won_item'] if results else None,
        'winning_index': WIN_INDEX,
        'tape': results[0]['tape'] if results else [],
        'inventory_id': results[0]['inventory_id'] if results else None,
        'opening_id': results[0]['opening_id'] if results else None,
        'server_seed_hash': results[0]['server_seed_hash'] if results else '',
    })

def open_case_by_id_api(request, case_id):
    """API alias for opening by case ID instead of slug."""
    return open_case_api(request, case_id=case_id)

@rate_limit(key_prefix='redeem_promo', limit=10, period=60, by_user=True)
@login_required
@require_POST
@transaction.atomic
def redeem_promocode_api(request):
    ip = get_client_ip(request)
    code_raw = request.POST.get('code', '').strip().upper()
    
    if not code_raw:
        return JsonResponse({'success': False, 'error': 'Пожалуйста, введите промокод.'}, status=400)

    # 1. Fetch promo code under row lock
    try:
        promo = PromoCode.objects.select_for_update().get(code=code_raw)
    except PromoCode.DoesNotExist:
        return JsonResponse({'success': False, 'error': '✕ Промокод не найден.'}, status=404)

    now = timezone.now()

    # 2. Status and validity checks
    if not promo.is_active:
        return JsonResponse({'success': False, 'error': '✕ Данный промокод выключен.'}, status=400)

    if promo.starts_at > now:
        return JsonResponse({'success': False, 'error': '✕ Срок действия промокода еще не начался.'}, status=400)

    if promo.expires_at < now:
        return JsonResponse({'success': False, 'error': '✕ Срок действия промокода истёк.'}, status=400)

    if promo.used_count >= promo.max_uses:
        return JsonResponse({'success': False, 'error': '✕ Лимит использований промокода исчерпан.'}, status=400)

    # 3. Check unique usage
    if PromoCodeUse.objects.filter(user=request.user, promo_code=promo).exists():
        return JsonResponse({'success': False, 'error': '✕ Вы уже активировали этот промокод ранее.'}, status=400)

    # 4. Check min deposit condition
    if promo.min_deposit > Decimal('0.00'):
        user_deposits = Transaction.objects.filter(
            user=request.user,
            transaction_type='deposit',
            status='completed'
        ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
        
        if user_deposits < promo.min_deposit:
            return JsonResponse({
                'success': False,
                'error': f'✕ Для активации промокода требуется сумма пополнений от {promo.min_deposit:.2f} UC.'
            }, status=400)

    # 5. Apply Bonus
    ledger_tx = None
    bonus_amount_applied = Decimal('0.00')
    msg = ""

    if promo.bonus_type == 'coins':
        bonus_amount_applied = promo.bonus_value
        ledger_tx = modify_user_balance(
            user=request.user,
            amount_delta=promo.bonus_value,
            transaction_type='promo_bonus',
            reference_id=f"promo:{promo.id}",
            description=f"Активация промокода {promo.code} (+{promo.bonus_value:.2f} UC)",
            ip_address=ip
        )
        msg = f"✓ Промокод активирован! Начислено +{promo.bonus_value:.2f} UC."

    elif promo.bonus_type == 'free_case_opens':
        free_count = int(promo.bonus_value)
        user_free, _ = UserFreeOpening.objects.select_for_update().get_or_create(
            user=request.user,
            case=promo.case,
            defaults={'openings_left': 0, 'total_granted': 0, 'promo_code': promo}
        )
        user_free.openings_left += free_count
        user_free.total_granted += free_count
        user_free.promo_code = promo
        user_free.save(update_fields=['openings_left', 'total_granted', 'promo_code', 'updated_at'])
        
        bonus_amount_applied = Decimal(str(free_count))
        msg = f"✓ Промокод активирован! Начислено {free_count} бесплатных открытий кейса «{promo.case.name}»."

    elif promo.bonus_type == 'percentage':
        bonus_pct = promo.bonus_value
        bonus_amount_applied = bonus_pct
        msg = f"✓ Промокод активирован! Бонус +{bonus_pct}% будет применен к следующему пополнению."

    # 6. Record PromoCodeUse & increment counter
    PromoCodeUse.objects.create(
        promo_code=promo,
        user=request.user,
        bonus_amount=bonus_amount_applied,
        related_transaction=ledger_tx
    )

    promo.used_count += 1
    promo.save(update_fields=['used_count'])

    profile = Profile.objects.get(user=request.user)

    audit_logger.info(
        f"PROMO_REDEEMED: user={request.user.username} (id={request.user.id}) | "
        f"code={promo.code} | type={promo.bonus_type} | bonus={bonus_amount_applied} | ip={ip}"
    )

    return JsonResponse({
        'success': True,
        'message': msg,
        'bonus_type': promo.bonus_type,
        'bonus_value': float(promo.bonus_value),
        'bonus': float(promo.bonus_value),
        'new_balance': float(profile.balance),
    })

@rate_limit(key_prefix='live_drops', limit=60, period=60, by_user=False)
def live_drops_api(request):
    openings = Opening.objects.select_related('user', 'case', 'item').order_by('-created_at')[:15]
    data = []
    for op in openings:
        data.append({
            'id': op.id,
            'username': op.user.username,
            'user_avatar': op.user.profile.display_avatar,
            'case_name': op.case.name,
            'item_name': op.item.name,
            'weapon_type': op.item.weapon_type,
            'skin_name': op.item.skin_name,
            'item_value': float(op.item.value),
            'rarity': op.item.rarity,
            'rarity_color': op.item.rarity_color,
            'image_url': op.item.image_url or (op.item.image.url if op.item.image else ''),
        })
    return JsonResponse({'success': True, 'drops': data})

def top_view(request):
    top_profiles = Profile.objects.filter(total_winnings__gt=0).select_related('user').order_by('-total_winnings')[:25]
    context = {
        'top_profiles': top_profiles,
        'active_tab': 'top',
    }
    return render(request, 'top.html', context)

def provably_fair_view(request):
    return render(request, 'provably_fair.html', {'active_tab': 'fairness'})

@rate_limit(key_prefix='verify_seed', limit=30, period=60, by_user=False)
def provably_fair_verify_api(request):
    server_seed = request.GET.get('server_seed', '').strip()
    client_seed = request.GET.get('client_seed', '').strip()
    nonce_raw = request.GET.get('nonce', '1').strip()
    
    if not server_seed or not client_seed:
        return JsonResponse({'success': False, 'error': 'Server seed и Client seed обязательны для проверки.'}, status=400)
        
    try:
        nonce = int(nonce_raw)
        if nonce < 1:
            nonce = 1
    except ValueError:
        nonce = 1
        
    calculated_hash = hash_seed(server_seed)
    calculated_roll = calculate_provably_fair_roll(server_seed, client_seed, nonce)
    
    return JsonResponse({
        'success': True,
        'server_seed': server_seed,
        'server_seed_hash': calculated_hash,
        'client_seed': client_seed,
        'nonce': nonce,
        'roll_float': calculated_roll,
        'roll_percent': round(calculated_roll * 100.0, 4),
    })

def custom_bad_request_view(request, exception=None):
    return render(request, '400.html', status=400)

def custom_permission_denied_view(request, exception=None):
    return render(request, '403.html', status=403)

def custom_csrf_failure_view(request, reason=""):
    return render(request, '403_csrf.html', {'reason': reason}, status=403)

def custom_page_not_found_view(request, exception=None):
    return render(request, '404.html', status=404)

def custom_server_error_view(request):
    return render(request, '500.html', status=500)

