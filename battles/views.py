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
    finished_battles = Battle.objects.filter(status='finished').select_related('creator', 'winner', 'case').order_by('-created_at')[:10]
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
        
    cost = battle.total_cost
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
        
    p2 = BattlePlayer.objects.create(battle=battle, user=request.user, is_bot=False)
    p1 = battle.players.filter(user=battle.creator).first()
    if not p1:
        p1 = BattlePlayer.objects.create(battle=battle, user=battle.creator, is_bot=False)
    
    # Execute rounds
    case_items = list(battle.case.case_items.select_related('item').all())
    p1_total = Decimal('0.00')
    p2_total = Decimal('0.00')
    
    for r in range(1, battle.rounds_count + 1):
        s_seed1 = generate_server_seed()
        ci1, _, _ = select_weighted_item(case_items, s_seed1, secrets.token_hex(8), r)
        BattleRound.objects.create(battle=battle, player=p1, round_number=r, item=ci1.item)
        p1_total += ci1.item.value
        
        s_seed2 = generate_server_seed()
        ci2, _, _ = select_weighted_item(case_items, s_seed2, secrets.token_hex(8), r)
        BattleRound.objects.create(battle=battle, player=p2, round_number=r, item=ci2.item)
        p2_total += ci2.item.value
        
    p1.total_loot_value = p1_total
    p1.save(update_fields=['total_loot_value'])
    p2.total_loot_value = p2_total
    p2.save(update_fields=['total_loot_value'])
    
    winner = p1.user if p1_total >= p2_total else p2.user
    battle.winner = winner
    battle.status = 'finished'
    battle.save(update_fields=['winner', 'status'])
    
    # Give all won items to the winner
    won_rounds = BattleRound.objects.filter(battle=battle).select_related('item')
    for br in won_rounds:
        InventoryItem.objects.create(user=winner, item=br.item, source='battle')
    winner.profile.total_winnings += (p1_total + p2_total)
    winner.profile.save(update_fields=['total_winnings'])
    
    audit_logger.info(
        f"BATTLE_COMPLETED: id={battle.id} | p1={p1.user.username} (${p1_total}) vs p2={p2.user.username} (${p2_total}) | winner={winner.username}"
    )

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
    rounds_count_raw = request.POST.get('rounds_count', 1)
    try:
        rounds_count = int(rounds_count_raw)
        if rounds_count not in (1, 2, 3, 5):
            rounds_count = 1
    except (ValueError, TypeError):
        rounds_count = 1
        
    vs_bot = request.POST.get('vs_bot', 'false').lower() == 'true'
    
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
        total_cost=cost,
        is_bot_opponent=vs_bot,
        status='finished' if vs_bot else 'waiting'
    )
    
    p1 = BattlePlayer.objects.create(battle=battle, user=request.user, is_bot=False)
    
    if vs_bot:
        p2 = BattlePlayer.objects.create(battle=battle, user=None, is_bot=True, bot_name='CyberBot AI')
        
        # Execute rounds
        case_items = list(case.case_items.select_related('item').all())
        p1_total = Decimal('0.00')
        p2_total = Decimal('0.00')
        
        for r in range(1, rounds_count + 1):
            s_seed1 = generate_server_seed()
            ci1, _, _ = select_weighted_item(case_items, s_seed1, secrets.token_hex(8), r)
            BattleRound.objects.create(battle=battle, player=p1, round_number=r, item=ci1.item)
            p1_total += ci1.item.value
            
            s_seed2 = generate_server_seed()
            ci2, _, _ = select_weighted_item(case_items, s_seed2, secrets.token_hex(8), r)
            BattleRound.objects.create(battle=battle, player=p2, round_number=r, item=ci2.item)
            p2_total += ci2.item.value
            
        p1.total_loot_value = p1_total
        p1.save(update_fields=['total_loot_value'])
        p2.total_loot_value = p2_total
        p2.save(update_fields=['total_loot_value'])
        
        human_won = p1_total >= p2_total
        battle.winner = request.user if human_won else None
        battle.status = 'finished'
        battle.save(update_fields=['winner', 'status'])
        
        # If human won, give won items from battle to inventory
        if human_won:
            won_rounds = BattleRound.objects.filter(battle=battle).select_related('item')
            for br in won_rounds:
                InventoryItem.objects.create(user=request.user, item=br.item, source='battle')
            request.user.profile.total_winnings += (p1_total + p2_total)
            request.user.profile.save(update_fields=['total_winnings'])

    audit_logger.info(
        f"BATTLE_CREATED: user={request.user.username} (id={request.user.id}) | "
        f"case={case.name} (${cost}) | vs_bot={vs_bot} | battle_id={battle.id} | ip={ip}"
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
    rounds = battle.rounds.select_related('player__user', 'item').order_by('round_number', 'id')
    
    context = {
        'battle': battle,
        'players': players,
        'rounds': rounds,
        'active_tab': 'battles',
    }
    return render(request, 'battle_detail.html', context)
