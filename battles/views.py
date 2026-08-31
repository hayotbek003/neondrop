import logging
import secrets
import random
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.db import transaction
from django.contrib.auth.models import User

from .models import Battle, BattlePlayer, BattleRound
from cases.models import Case, Item, CaseItem
from inventory.models import InventoryItem
from cases.provably_fair import generate_server_seed, select_weighted_item, hash_seed
from payments.services import modify_user_balance, InsufficientBalanceError
from config.security import rate_limit, get_client_ip

security_logger = logging.getLogger('neondrop.security')
audit_logger = logging.getLogger('neondrop.audit')

@login_required
def index_view(request):
    open_battles = Battle.objects.filter(status='waiting').select_related('creator', 'case').order_by('-created_at')
    finished_battles = Battle.objects.filter(status='completed').select_related('creator', 'winner', 'case').order_by('-created_at')[:10]
    available_cases = Case.objects.filter(active=True).order_by('price')
    
    context = {
        'open_battles': open_battles,
        'finished_battles': finished_battles,
        'available_cases': available_cases,
        'active_tab': 'battles',
    }
    return render(request, 'battles.html', context)

battles_view = index_view

@rate_limit(key_prefix='battle_join', limit=15, period=60, by_user=True)
@login_required
@require_POST
@transaction.atomic
def join_battle_api(request, battle_id):
    ip = get_client_ip(request)
    battle = get_object_or_404(Battle.objects.select_for_update(), id=battle_id, status='waiting')
    
    if battle.creator == request.user:
        return JsonResponse({'success': False, 'error': 'Вы не можете присоединиться к собственной битве.'}, status=400)
        
    cost = battle.cost_per_player
    try:
        ledger_tx = modify_user_balance(
            user=request.user,
            amount_delta=-cost,
            transaction_type='battle_entry',
            reference_id=f"battle_join:{battle.id}",
            description=f"Взнос за участие в битве #{battle.id}",
            ip_address=ip
        )
    except InsufficientBalanceError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
        
    p2 = BattlePlayer.objects.create(battle=battle, user=request.user, position=2)
    p1 = battle.players.get(position=1)
    
    # Execute rounds
    case_items = list(battle.case.case_items.select_related('item').all())
    p1_total = Decimal('0.00')
    p2_total = Decimal('0.00')
    
    for r in range(1, battle.rounds_count + 1):
        s_seed1 = generate_server_seed()
        ci1, _, _ = select_weighted_item(case_items, s_seed1, secrets.token_hex(8), r)
        BattleRound.objects.create(battle=battle, player=p1, round_number=r, item=ci1.item, item_value=ci1.item.value)
        p1_total += ci1.item.value
        
        s_seed2 = generate_server_seed()
        ci2, _, _ = select_weighted_item(case_items, s_seed2, secrets.token_hex(8), r)
        BattleRound.objects.create(battle=battle, player=p2, round_number=r, item=ci2.item, item_value=ci2.item.value)
        p2_total += ci2.item.value
        
    p1.total_value = p1_total
    p1.save(update_fields=['total_value'])
    p2.total_value = p2_total
    p2.save(update_fields=['total_value'])
    
    winner = p1.user if p1_total >= p2_total else p2.user
    battle.winner = winner
    battle.status = 'completed'
    battle.save(update_fields=['winner', 'status'])
    
    # Give all won items to the winner
    won_rounds = BattleRound.objects.filter(battle=battle).select_related('item')
    for br in won_rounds:
        InventoryItem.objects.create(user=winner, item=br.item, source='battle')
    winner.profile.total_winnings += (p1_total + p2_total)
    winner.profile.save(update_fields=['total_winnings'])
    
    return JsonResponse({
        'success': True,
        'battle_id': battle.id,
        'redirect_url': f"/battles/{battle.id}/",
        'new_balance': float(ledger_tx.balance_after),
    })

@rate_limit(key_prefix='battle_create', limit=10, period=60, by_user=True)
@login_required
@require_POST
@transaction.atomic
def create_battle_api(request):
    ip = get_client_ip(request)
    case_id = request.POST.get('case_id')
    rounds_count = int(request.POST.get('rounds_count', 1))
    mode = request.POST.get('mode', '1v1_bot')
    
    case = get_object_or_404(Case, id=case_id, active=True)
    cost = case.price * rounds_count
    
    # 1. Deduct cost from creator's balance atomically
    try:
        ledger_tx = modify_user_balance(
            user=request.user,
            amount_delta=-cost,
            transaction_type='battle_entry',
            reference_id=f"case:{case.id}",
            description=f"Взнос за участие в битве кейсов «{case.name}» ({rounds_count} раунд.)",
            ip_address=ip
        )
    except InsufficientBalanceError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
        
    battle = Battle.objects.create(
        creator=request.user,
        case=case,
        rounds_count=rounds_count,
        mode=mode,
        cost_per_player=cost,
        status='waiting' if mode == '1v1_pvp' else 'in_progress'
    )
    
    p1 = BattlePlayer.objects.create(battle=battle, user=request.user, position=1)
    
    if mode == '1v1_bot':
        bot_user, _ = User.objects.get_or_create(username='NeonBot_AI', defaults={'email': 'bot@neondrop.gg'})
        p2 = BattlePlayer.objects.create(battle=battle, user=bot_user, is_bot=True, position=2)
        
        # Execute rounds
        case_items = list(case.case_items.select_related('item').all())
        p1_total = Decimal('0.00')
        p2_total = Decimal('0.00')
        
        for r in range(1, rounds_count + 1):
            s_seed1 = generate_server_seed()
            ci1, _, _ = select_weighted_item(case_items, s_seed1, secrets.token_hex(8), r)
            BattleRound.objects.create(battle=battle, player=p1, round_number=r, item=ci1.item, item_value=ci1.item.value)
            p1_total += ci1.item.value
            
            s_seed2 = generate_server_seed()
            ci2, _, _ = select_weighted_item(case_items, s_seed2, secrets.token_hex(8), r)
            BattleRound.objects.create(battle=battle, player=p2, round_number=r, item=ci2.item, item_value=ci2.item.value)
            p2_total += ci2.item.value
            
        p1.total_value = p1_total
        p1.save(update_fields=['total_value'])
        p2.total_value = p2_total
        p2.save(update_fields=['total_value'])
        
        winner = request.user if p1_total >= p2_total else bot_user
        battle.winner = winner
        battle.status = 'completed'
        battle.save(update_fields=['winner', 'status'])
        
        # If human won, give won items from battle to inventory
        if winner == request.user:
            won_rounds = BattleRound.objects.filter(battle=battle).select_related('item')
            for br in won_rounds:
                InventoryItem.objects.create(user=request.user, item=br.item, source='battle')
            request.user.profile.total_winnings += (p1_total + p2_total)
            request.user.profile.save(update_fields=['total_winnings'])

    audit_logger.info(
        f"BATTLE_CREATED: user={request.user.username} (id={request.user.id}) | "
        f"case={case.name} (${cost}) | mode={mode} | battle_id={battle.id} | ip={ip}"
    )

    return JsonResponse({
        'success': True,
        'battle_id': battle.id,
        'redirect_url': f"/battles/{battle.id}/",
        'new_balance': float(ledger_tx.balance_after),
    })

@login_required
def battle_detail_view(request, battle_id):
    battle = get_object_or_404(Battle.objects.select_related('creator', 'winner', 'case'), id=battle_id)
    players = battle.players.select_related('user').all()
    rounds = battle.rounds.select_related('player__user', 'item').order_by('round_number', 'player__position')
    
    context = {
        'battle': battle,
        'players': players,
        'rounds': rounds,
        'active_tab': 'battles',
    }
    return render(request, 'battle_detail.html', context)
