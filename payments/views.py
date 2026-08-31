import logging
import urllib.parse
from decimal import Decimal
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.conf import settings

from .models import Transaction
from config.security import rate_limit, get_client_ip

security_logger = logging.getLogger('neondrop.security')
audit_logger = logging.getLogger('neondrop.audit')

@login_required
def deposit_view(request):
    transactions = Transaction.objects.filter(user=request.user, transaction_type='deposit').order_by('-created_at')[:20]
    return render(request, 'deposit.html', {
        'transactions': transactions,
        'active_tab': 'deposit',
        'telegram_bot': getattr(settings, 'TELEGRAM_BOT_USERNAME', 'YOUR_TELEGRAM_USERNAME'),
    })

@rate_limit(key_prefix='deposit_req', limit=10, period=60, by_user=True)
@login_required
@require_POST
def create_deposit_request_api(request):
    ip = get_client_ip(request)
    amount_raw = request.POST.get('amount', '').strip()
    
    try:
        amount = Decimal(amount_raw)
        if amount < Decimal('1.00') or amount > Decimal('50000.00'):
            return JsonResponse({'success': False, 'error': 'Сумма пополнения должна быть от $1.00 до $50,000.00.'}, status=400)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Некорректная сумма пополнения.'}, status=400)

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
        description=f"Заявка на пополнение через Telegram на сумму ${amount:.2f}"
    )

    audit_logger.info(
        f"DEPOSIT_REQUEST_CREATED: user={request.user.username} (id={request.user.id}) | "
        f"amount=${amount} | tx_id={tx.id} | ip={ip}"
    )

    # Format Telegram direct message URL
    tg_bot = getattr(settings, 'TELEGRAM_BOT_USERNAME', 'YOUR_TELEGRAM_USERNAME')
    msg_template = (
        f"Здравствуйте! Хочу пополнить баланс.\n"
        f"Пользователь: {request.user.username}\n"
        f"Сумма: ${amount:.2f}\n"
        f"ID: {request.user.id}\n"
        f"Номер заявки: #{tx.id}"
    )
    encoded_msg = urllib.parse.quote(msg_template)
    telegram_url = f"https://t.me/{tg_bot}?text={encoded_msg}"

    return JsonResponse({
        'success': True,
        'transaction_id': tx.id,
        'telegram_url': telegram_url,
        'message': 'Заявка успешно создана. Перейдите в Telegram для оплаты.'
    })
