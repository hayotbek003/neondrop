import logging
import urllib.parse
from decimal import Decimal
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from django.http import JsonResponse
from django.conf import settings
from django.db import transaction

from .models import Transaction, Withdrawal
from .currency import format_uc, format_usd_approx, format_uzs_approx, get_currency_rates
from config.security import rate_limit, get_client_ip
from users.models import Profile

security_logger = logging.getLogger('neondrop.security')
audit_logger = logging.getLogger('neondrop.audit')

@ensure_csrf_cookie
@login_required
def deposit_view(request):
    tg_admin = getattr(settings, 'TELEGRAM_BOT_USERNAME', 'neondrop_admin').lstrip('@')
    transactions = Transaction.objects.filter(user=request.user, transaction_type='deposit').order_by('-created_at')[:20]
    rates = get_currency_rates()
    return render(request, 'deposit.html', {
        'transactions': transactions,
        'active_tab': 'deposit',
        'telegram_admin': tg_admin,
        'currency_rates': rates,
    })

@rate_limit(key_prefix='deposit_req', limit=10, period=60, by_user=True)
@login_required
@require_POST
def create_deposit_request_api(request):
    ip = get_client_ip(request)
    amount_raw = request.POST.get('amount', '').strip()
    
    try:
        amount = Decimal(amount_raw)
        if amount < Decimal('1.00') or amount > Decimal('500000.00'):
            return JsonResponse({'success': False, 'error': 'Сумма пополнения должна быть от 1 UC до 500,000 UC.'}, status=400)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Некорректная сумма пополнения.'}, status=400)

    amount_display = format_uc(amount)
    usd_display = format_usd_approx(amount)
    uzs_display = format_uzs_approx(amount)

    # Create pending transaction record (NO AUTOMATIC BALANCE CREDIT)
    tx = Transaction.objects.create(
        user=request.user,
        amount=amount,
        balance_before=request.user.profile.balance,
        balance_after=request.user.profile.balance,
        transaction_type='deposit',
        status='pending',
        payment_method='telegram',
        telegram_username=request.user.profile.telegram_username,
        ip_address=ip,
        description=f"Заявка на пополнение через Telegram на сумму {amount_display} ({uzs_display} / {usd_display})"
    )

    audit_logger.info(
        f"DEPOSIT_REQUEST_CREATED: user={request.user.username} (id={request.user.id}) | "
        f"amount={amount_display} | tx_id={tx.id} | ip={ip}"
    )

    # Format Telegram administrator direct link with exact required pre-filled text
    tg_admin = getattr(settings, 'TELEGRAM_BOT_USERNAME', 'neondrop_admin').lstrip('@')
    
    msg_template = (
        f"Здравствуйте! Хочу пополнить баланс NEONDROP.\n\n"
        f"Мой логин: {request.user.username}\n"
        f"Мой ID: {request.user.id}\n"
        f"Сумма пополнения: {amount_display} ({uzs_display} / {usd_display})"
    )
    encoded_msg = urllib.parse.quote(msg_template)
    telegram_url = f"https://t.me/{tg_admin}?text={encoded_msg}"

    return JsonResponse({
        'success': True,
        'transaction_id': tx.id,
        'telegram_url': telegram_url,
        'message': 'Заявка успешно создана. Перейдите в Telegram для отправки сообщения администратору.'
    })


@rate_limit(key_prefix='withdraw_req', limit=10, period=60, by_user=True)
@login_required
@require_POST
def create_withdrawal_request_api(request):
    ip = get_client_ip(request)
    amount_raw = request.POST.get('amount', '').strip()
    method = request.POST.get('method', '').strip()
    details = request.POST.get('details', '').strip()

    if not method:
        return JsonResponse({'success': False, 'error': 'Пожалуйста, укажите способ получения.'}, status=400)

    if not details:
        return JsonResponse({'success': False, 'error': 'Пожалуйста, укажите ваши реквизиты.'}, status=400)

    try:
        amount_dec = Decimal(amount_raw)
        if amount_dec <= Decimal('0'):
            return JsonResponse({'success': False, 'error': 'Сумма вывода должна быть больше нуля.'}, status=400)
        if amount_dec % 1 != 0:
            return JsonResponse({'success': False, 'error': 'Сумма вывода должна быть целым числом UC.'}, status=400)
        amount_int = int(amount_dec)
        if amount_int < 60:
            return JsonResponse({'success': False, 'error': 'Минимальная сумма вывода — 60 UC.'}, status=400)
        amount = Decimal(amount_int)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Некорректная сумма вывода.'}, status=400)

    # Atomic balance deduction and withdrawal creation with row lock
    with transaction.atomic():
        profile = Profile.objects.select_for_update().get(user=request.user)
        if profile.balance < amount:
            cur_bal = int(profile.balance) if profile.balance % 1 == 0 else f"{profile.balance:.2f}"
            return JsonResponse({
                'success': False,
                'error': f'Недостаточно средств. Ваш баланс: {cur_bal} UC, запрошено: {amount_int} UC.'
            }, status=400)

        # 1. Deduct UC immediately
        balance_before = profile.balance
        profile.balance -= amount
        profile.save(update_fields=['balance'])
        balance_after = profile.balance

        # 2. Create pending Withdrawal record
        w = Withdrawal.objects.create(
            user=request.user,
            username=request.user.username,
            user_id_val=request.user.id,
            amount=amount,
            method=method,
            details=details,
            status='pending'
        )

        # 3. Create immutable Transaction record for the deduction
        tx = Transaction.objects.create(
            user=request.user,
            amount=-amount,
            balance_before=balance_before,
            balance_after=balance_after,
            transaction_type='withdraw',
            status='completed',
            payment_method='telegram',
            reference_id=f"withdrawal:{w.id}",
            description=f"Вывод UC #{w.id} ({method}: {details})",
            comment=details,
            ip_address=ip
        )

        w.related_transaction = tx
        w.save(update_fields=['related_transaction'])

    audit_logger.info(
        f"WITHDRAWAL_REQUEST_CREATED: user={request.user.username} (id={request.user.id}) | "
        f"amount={amount} UC | balance_before={balance_before} | balance_after={balance_after} | "
        f"withdrawal_id={w.id} | method={method} | ip={ip}"
    )

    tg_admin = getattr(settings, 'TELEGRAM_BOT_USERNAME', 'neondrop_admin').lstrip('@')
    created_at_str = w.created_at.strftime('%d.%m.%Y %H:%M')
    balance_after_display = f"{int(balance_after)}" if balance_after % 1 == 0 else f"{balance_after:.2f}"

    # Telegram format:
    # 🔔 НОВЫЙ ВЫВОД NEONDROP
    # Заявка №: {withdrawal_id}
    # 👤 Пользователь: {username}
    # 🆔 ID: {user_id}
    # 💰 Сумма: {amount_uc} UC
    # 📤 Способ получения:
    # {method}
    # 📋 Реквизиты:
    # {details}
    # 💳 Баланс после вывода:
    # {balance_after} UC
    # 📅 Дата:
    # {created_at}
    # Статус: ОЖИДАЕТ ВЫПЛАТЫ
    msg_template = (
        f"🔔 НОВЫЙ ВЫВОД NEONDROP\n\n"
        f"Заявка №: {w.id}\n\n"
        f"👤 Пользователь: {request.user.username}\n"
        f"🆔 ID: {request.user.id}\n\n"
        f"💰 Сумма: {amount_int} UC\n\n"
        f"📤 Способ получения:\n"
        f"{method}\n\n"
        f"📋 Реквизиты:\n"
        f"{details}\n\n"
        f"💳 Баланс после вывода:\n"
        f"{balance_after_display} UC\n\n"
        f"📅 Дата:\n"
        f"{created_at_str}\n\n"
        f"Статус: ОЖИДАЕТ ВЫПЛАТЫ"
    )

    encoded_msg = urllib.parse.quote(msg_template)
    telegram_url = f"https://t.me/{tg_admin}?text={encoded_msg}"

    return JsonResponse({
        'success': True,
        'withdrawal_id': w.id,
        'balance_after': balance_after_display,
        'telegram_url': telegram_url,
        'message': f'Заявка на вывод #{w.id} создана. С баланса списано {amount_int} UC.'
    })

