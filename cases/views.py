import logging
import secrets
import random
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.http import JsonResponse
from django.db import transaction
from django.contrib.auth.models import User

from .models import Case, Item, CaseItem, Opening, Category
from .provably_fair import (
    generate_server_seed, 
    calculate_provably_fair_roll, 
    select_weighted_item, 
    hash_seed
)
from inventory.models import InventoryItem
from users.models import Profile
from payments.services import modify_user_balance, InsufficientBalanceError
from config.security import rate_limit, check_and_store_idempotency_key, get_client_ip

security_logger = logging.getLogger('neondrop.security')
audit_logger = logging.getLogger('neondrop.audit')

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
        'contracts': 258148 + InventoryItem.objects.filter(source='contract').count(),
        'online_users': random.randint(520, 680),
    }
    
    # Top winners leaderboard
    top_profiles = Profile.objects.filter(total_winnings__gt=0).select_related('user').order_by('-total_winnings')[:5]
    top_winners = []
    
    mock_weapons = [
        {'weapon': 'Karambit', 'skin': 'Fade', 'image': 'knife_karambit_fade'},
        {'weapon': 'M4A4', 'skin': 'Howl', 'image': 'm4a4_howl'},
        {'weapon': 'AWP', 'skin': 'Dragon Lore', 'image': 'awp_dragon_lore'},
        {'weapon': 'AK-47', 'skin': 'Neon Rider', 'image': 'ak47_neon_rider'},
        {'weapon': 'Desert Eagle', 'skin': 'Printstream', 'image': 'deagle_printstream'},
    ]
    
    if top_profiles.exists():
        for i, prof in enumerate(top_profiles):
            weapon_info = mock_weapons[i % len(mock_weapons)]
            top_winners.append({
                'rank': i + 1,
                'username': prof.user.username,
                'avatar': prof.display_avatar,
                'winnings': prof.total_winnings,
                'weapon': weapon_info['weapon'],
                'skin': weapon_info['skin'],
                'weapon_image': weapon_info['image'],
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
    
    if active_category == 'popular':
        cases = cases.filter(is_popular=True)
    elif active_category == 'new':
        cases = cases.filter(is_new=True)
    elif active_category == 'affordable' and request.user.is_authenticated:
        cases = cases.filter(price__lte=request.user.profile.balance)
    elif active_category != 'all' and active_category != '':
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

def case_detail_view(request, slug):
    case = get_object_or_404(Case.objects.prefetch_related('case_items__item'), slug=slug, active=True)
    case_items = case.case_items.select_related('item').all().order_by('-item__value')
    
    # Calculate percentage chance for each item
    total_weight = sum(ci.weight for ci in case_items)
    items_with_chances = []
    for ci in case_items:
        chance_percent = (ci.weight / total_weight * 100.0) if total_weight > 0 else 0.0
        items_with_chances.append({
            'case_item': ci,
            'item': ci.item,
            'chance_percent': round(chance_percent, 2 if chance_percent >= 0.1 else 3),
        })
        
    context = {
        'case': case,
        'items_with_chances': items_with_chances,
        'active_tab': 'cases',
    }
    return render(request, 'case_detail.html', context)

@rate_limit(key_prefix='open_case', limit=20, period=60, by_user=True)
@login_required
@require_POST
@transaction.atomic
def open_case_api(request, slug):
    ip = get_client_ip(request)
    idempotency_key = request.POST.get('idempotency_key') or request.headers.get('X-Idempotency-Key')
    
    # 1. Idempotency protection against rapid double-clicks
    if idempotency_key:
        if not check_and_store_idempotency_key(request.user.id, idempotency_key, f"open_case_{slug}"):
            return JsonResponse({
                'success': False,
                'error': 'Запрос на открытие уже обрабатывается. Пожалуйста, подождите.'
            }, status=409)

    # 2. Server-side load of case from database
    case = get_object_or_404(Case, slug=slug, active=True)
    case_items = list(case.case_items.select_related('item').all())
    
    if not case_items:
        return JsonResponse({'success': False, 'error': 'Кейс временно недоступен.'}, status=400)

    # 3. Deduct balance via authoritative ledger service with select_for_update row lock
    try:
        ledger_tx = modify_user_balance(
            user=request.user,
            amount_delta=-case.price,
            transaction_type='case_open',
            reference_id=f"case:{case.id}",
            description=f"Открытие кейса «{case.name}»",
            idempotency_key=idempotency_key,
            ip_address=ip
        )
    except InsufficientBalanceError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    except Exception as e:
        security_logger.error(f"Balance deduction error for user {request.user.id}: {e}")
        return JsonResponse({'success': False, 'error': 'Ошибка транзакции списания средств.'}, status=500)

    profile = request.user.profile
    profile = type(profile).objects.select_for_update().get(id=profile.id)

    # 4. Provably Fair Item Selection
    server_seed = generate_server_seed()
    client_seed = request.POST.get('client_seed') or secrets.token_hex(16)
    # Sanitize client seed (limit length and alphanumeric characters)
    client_seed = ''.join(c for c in client_seed if c.isalnum())[:64] or secrets.token_hex(16)
    nonce = profile.total_opened + 1
    
    selected_ci, roll_float, server_seed_hash = select_weighted_item(case_items, server_seed, client_seed, nonce)
    won_item = selected_ci.item
    
    # 5. Record Opening in Database
    opening = Opening.objects.create(
        user=request.user,
        case=case,
        item=won_item,
        price=case.price,
        server_seed_hash=server_seed_hash,
        server_seed=server_seed,
        client_seed=client_seed,
        nonce=nonce
    )
    
    # 6. Add Won Item to User Inventory
    inv_item = InventoryItem.objects.create(
        user=request.user,
        item=won_item,
        source='case',
        opening=opening
    )
    
    # 7. Update Profile Statistics
    profile.total_opened += 1
    profile.total_winnings += won_item.value
    profile.save(update_fields=['total_opened', 'total_winnings'])
    
    audit_logger.info(
        f"CASE_OPEN_SUCCESS: user={request.user.username} (id={request.user.id}) | "
        f"case={case.name} (${case.price}) | won={won_item.name} (${won_item.value}) | "
        f"roll={roll_float:.8f} | hash={server_seed_hash} | opening_id={opening.id}"
    )

    # 8. Build Roulette Tape (65 items with winning item placed at fixed index 50)
    WIN_INDEX = 50
    tape = []
    all_items = [ci.item for ci in case_items]
    
    for i in range(65):
        if i == WIN_INDEX:
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
        
    return JsonResponse({
        'success': True,
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
        'inventory_id': inv_item.id,
        'new_balance': float(ledger_tx.balance_after),
        'server_seed_hash': server_seed_hash,
        'server_seed': server_seed,
        'client_seed': client_seed,
        'nonce': nonce,
        'roll_float': roll_float,
        'tape': tape,
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

def custom_page_not_found_view(request, exception=None):
    return render(request, '404.html', status=404)

def custom_server_error_view(request):
    return render(request, '500.html', status=500)
