import logging
import urllib.parse
from decimal import Decimal
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from django.http import JsonResponse
from django.conf import settings

from .models import Transaction
from .currency import format_uc, format_usd_approx, format_uzs_approx, get_currency_rates
from config.security import rate_limit, get_client_ip

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
