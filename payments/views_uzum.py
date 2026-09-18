import json
import logging
import uuid
from decimal import Decimal
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.db import transaction

from .models import UCPackage, UzumPayment, Transaction
from .uzum_client import UzumClient
from .services import modify_user_balance
from config.security import rate_limit, get_client_ip

audit_logger = logging.getLogger('neondrop.audit')
security_logger = logging.getLogger('neondrop.security')


@rate_limit(key_prefix='uzum_pay', limit=15, period=60, by_user=True)
@login_required
@require_POST
def create_uzum_payment_api(request):
    """
    Creates a pending Uzum Checkout payment for a selected UC Package.
    Calculates authoritative price on backend and registers the order with Uzum.
    """
    package_id = request.POST.get('package_id', '').strip()
    uc_amount_raw = request.POST.get('uc_amount', '').strip()

    package = None
    if package_id and package_id.isdigit():
        package = UCPackage.objects.filter(id=int(package_id), is_active=True).first()
    elif uc_amount_raw and uc_amount_raw.isdigit():
        package = UCPackage.objects.filter(uc_amount=int(uc_amount_raw), is_active=True).first()

    if not package:
        return JsonResponse({
            'success': False,
            'error': 'Выбранный пакет UC не найден или не активен.'
        }, status=400)

    # Calculate authoritative server price (applies blogger promo rate if user activated one)
    amount_uzs = package.get_actual_price_uzs(request.user)
    uc_amount = Decimal(package.uc_amount)

    # Check active blogger promo code for attribution
    from cases.models import PromoCodeUse
    blogger_use = PromoCodeUse.objects.filter(
        user=request.user
    ).select_related('promo_code').filter(
        promo_code__bonus_type='blogger',
        promo_code__is_active=True
    ).first()
    if not blogger_use:
        blogger_use = PromoCodeUse.objects.filter(
            user=request.user,
            promo_code__blogger_percentage__gt=0,
            promo_code__is_active=True
        ).select_related('promo_code').first()
    promo = blogger_use.promo_code if blogger_use else None

    # Generate unique order number
    order_number = f"ND-UZ-{uuid.uuid4().hex[:10].upper()}"
    client_ip = get_client_ip(request)

    # Create local UzumPayment record with pending status
    payment = UzumPayment.objects.create(
        order_number=order_number,
        user=request.user,
        package=package,
        uc_amount=uc_amount,
        amount_uzs=amount_uzs,
        status='pending',
        idempotency_key=f"uzum_pay_{order_number}",
        ip_address=client_ip,
        promo_code=promo
    )

    # Prepare redirect and callback URLs
    success_url = request.build_absolute_uri(reverse('payments:uzum_return')) + f"?order_id={order_number}"
    failure_url = request.build_absolute_uri(reverse('payments:uzum_return')) + f"?order_id={order_number}"
    callback_url = getattr(settings, 'UZUM_WEBHOOK_URL', '') or request.build_absolute_uri(reverse('payments:uzum_webhook'))

    details = f"Пополнение NEONDROP: {package.uc_amount} UC (Заказ #{order_number})"

    # Register payment with Uzum API
    reg_result = UzumClient.register_payment(
        order_number=order_number,
        amount_uzs=amount_uzs,
        client_id=str(request.user.id),
        success_url=success_url,
        failure_url=failure_url,
        payment_details=details,
        callback_url=callback_url
    )

    if not reg_result.get('success'):
        payment.status = 'failed'
        payment.error_message = reg_result.get('error', 'Ошибка регистрации платежа')
        payment.save(update_fields=['status', 'error_message', 'updated_at'])
        audit_logger.error(
            f"PAYMENT FAILED: order={order_number} | user={request.user.username} | "
            f"error={payment.error_message}"
        )
        return JsonResponse({'success': False, 'error': payment.error_message}, status=400)

    payment.uzum_order_id = reg_result.get('orderId')
    payment.payment_redirect_url = reg_result.get('paymentRedirectUrl')
    payment.save(update_fields=['uzum_order_id', 'payment_redirect_url', 'updated_at'])

    audit_logger.info(
        f"PAYMENT CREATED: user={request.user.username} (id={request.user.id}) | "
        f"order={order_number} | uzum_id={payment.uzum_order_id} | "
        f"uc={uc_amount} | uzs={amount_uzs} | ip={client_ip}"
    )

    return JsonResponse({
        'success': True,
        'order_number': order_number,
        'payment_url': payment.payment_redirect_url,
        'amount_uzs': int(amount_uzs),
        'uc_amount': int(uc_amount)
    })


@csrf_exempt
@require_POST
def uzum_webhook(request):
    """
    Authoritative Webhook Handler for Uzum Checkout.
    Verifies authenticity, ensures idempotency via select_for_update(),
    validates status against Uzum API, and credits UC strictly once.
    """
    client_ip = get_client_ip(request)
    audit_logger.info(f"PAYMENT CALLBACK RECEIVED: ip={client_ip}")

    raw_body = request.body
    signature = request.headers.get('X-Signature', '') or request.META.get('HTTP_X_SIGNATURE', '')

    # 1. Verify webhook authenticity (never credit on unverified requests)
    if not UzumClient.verify_signature(raw_body, signature):
        security_logger.warning(
            f"UNAUTHORIZED_UZUM_WEBHOOK: signature_mismatch | ip={client_ip} | "
            f"sig_header={signature[:20]}..."
        )
        return JsonResponse({'error': 'Invalid signature'}, status=403)

    try:
        payload = json.loads(raw_body.decode('utf-8'))
    except Exception as e:
        security_logger.warning(f"MALFORMED_UZUM_WEBHOOK: {e} | ip={client_ip}")
        return JsonResponse({'error': 'Malformed JSON body'}, status=400)

    # Extract identifiers
    order_number = payload.get('orderNumber') or payload.get('merchantOrderId') or payload.get('order_number')
    uzum_order_id = payload.get('orderId') or payload.get('transId') or payload.get('uzum_order_id')
    status_val = str(payload.get('status', '')).upper()
    amount_tiyin = payload.get('amount') or payload.get('totalAmount')

    if not order_number and not uzum_order_id:
        return JsonResponse({'error': 'Missing order identifier'}, status=400)

    # 2. Atomic row lock for strict idempotency
    with transaction.atomic():
        query = UzumPayment.objects.select_for_update()
        payment = None
        if order_number:
            payment = query.filter(order_number=order_number).first()
        if not payment and uzum_order_id:
            payment = query.filter(uzum_order_id=uzum_order_id).first()

        if not payment:
            security_logger.warning(
                f"UNKNOWN_PAYMENT_WEBHOOK: order={order_number}, uzum_id={uzum_order_id} | ip={client_ip}"
            )
            return JsonResponse({'error': 'Payment not found'}, status=404)

        # 3. Strict Idempotency: check if already processed
        if payment.status == 'paid':
            audit_logger.info(
                f"PAYMENT ALREADY PROCESSED: order={payment.order_number} | "
                f"payment_id={payment.id} | ip={client_ip}"
            )
            return JsonResponse({'status': 'OK', 'message': 'Payment already processed'})

        # 4. Verify payment status via official Uzum API
        uzum_verified = False
        uzum_status = "UNKNOWN"
        target_uzum_id = payment.uzum_order_id or uzum_order_id
        if target_uzum_id:
            status_info = UzumClient.get_order_status(target_uzum_id)
            uzum_status = str(status_info.get('status', '')).upper()
            if uzum_status in ('COMPLETED', 'SUCCESS'):
                uzum_verified = True
        elif status_val in ('COMPLETED', 'SUCCESS'):
            uzum_verified = True

        audit_logger.info(
            f"PAYMENT VERIFIED: order={payment.order_number} | "
            f"verified={uzum_verified} | uzum_status={uzum_status} | callback_status={status_val}"
        )

        # 5. Amount validation if amount provided in webhook
        if amount_tiyin:
            expected_tiyin = int((payment.amount_uzs * Decimal('100')).quantize(Decimal('1')))
            if int(amount_tiyin) != expected_tiyin:
                payment.status = 'failed'
                payment.error_message = f"Amount mismatch: expected {expected_tiyin} tiyin, got {amount_tiyin}"
                payment.raw_callback_data = payload
                payment.save(update_fields=['status', 'error_message', 'raw_callback_data', 'updated_at'])
                audit_logger.error(
                    f"PAYMENT FAILED: order={payment.order_number} | reason=amount_mismatch | "
                    f"expected={expected_tiyin} | actual={amount_tiyin}"
                )
                return JsonResponse({'error': 'Amount mismatch'}, status=400)

        # 6. If not verified as successful
        if not uzum_verified:
            if status_val in ('DECLINED', 'FAILED', 'ERROR'):
                payment.status = 'failed'
            elif status_val in ('CANCELLED', 'CANCELED'):
                payment.status = 'cancelled'
            payment.raw_callback_data = payload
            payment.save(update_fields=['status', 'raw_callback_data', 'updated_at'])
            audit_logger.warning(
                f"PAYMENT FAILED: order={payment.order_number} | status={payment.status}"
            )
            return JsonResponse({'status': 'OK', 'message': f'Payment marked as {payment.status}'})

        # 7. Authoritative UC credit via immutable ledger
        uzs_formatted = f"{int(payment.amount_uzs):,} UZS".replace(',', ' ')
        tx = modify_user_balance(
            user=payment.user,
            amount_delta=payment.uc_amount,
            transaction_type='deposit',
            reference_id=f"uzum:{payment.order_number}",
            description=f"Пополнение баланса через Uzum Checkout: +{payment.uc_amount} UC ({uzs_formatted})",
            payment_method='card',
            idempotency_key=f"uzum_tx_{payment.order_number}",
            ip_address=payment.ip_address
        )
        if payment.promo_code:
            tx.promo_code = payment.promo_code
            tx.save(update_fields=['promo_code'])

        # 8. Mark payment as paid
        payment.status = 'paid'
        payment.paid_at = timezone.now()
        payment.related_transaction = tx
        payment.raw_callback_data = payload
        payment.save(update_fields=['status', 'paid_at', 'related_transaction', 'raw_callback_data', 'updated_at'])

        audit_logger.info(
            f"BALANCE CREDITED: user={payment.user.username} (id={payment.user.id}) | "
            f"order={payment.order_number} | +{payment.uc_amount} UC | "
            f"balance_after={tx.balance_after} | tx_id={tx.id}"
        )

        return JsonResponse({'status': 'OK', 'result': 'CONFIRMED'})


@login_required
@require_GET
def uzum_return_view(request):
    """
    Return URL for Uzum Checkout.
    CRITICAL: This endpoint is strictly read-only and NEVER credits UC directly.
    It displays the current payment state and allows the UI to poll the backend.
    """
    order_id = request.GET.get('order_id', '').strip()
    payment = UzumPayment.objects.filter(order_number=order_id, user=request.user).first()
    is_mock = request.GET.get('mock_uzum') == '1'

    return render(request, 'uzum_return.html', {
        'order_id': order_id,
        'payment': payment,
        'is_mock': is_mock,
    })


@login_required
@require_GET
def uzum_status_api(request):
    """
    Read-only status API for frontend polling on the Return URL.
    """
    order_id = request.GET.get('order_id', '').strip()
    payment = UzumPayment.objects.filter(order_number=order_id, user=request.user).first()

    if not payment:
        return JsonResponse({'success': False, 'error': 'Платеж не найден'}, status=404)

    return JsonResponse({
        'success': True,
        'status': payment.status,
        'uc_amount': int(payment.uc_amount) if payment.uc_amount % 1 == 0 else float(payment.uc_amount),
        'amount_uzs': int(payment.amount_uzs),
        'is_paid': payment.status == 'paid',
        'is_failed': payment.status in ('failed', 'cancelled'),
    })


@csrf_exempt
@require_POST
def simulate_sandbox_webhook_api(request):
    """
    Development/Sandbox only helper: triggers local webhook to complete payment in dev mode.
    Disabled in production.
    """
    if not (getattr(settings, 'DEBUG', False) or getattr(settings, 'UZUM_TEST_MODE', False)):
        return JsonResponse({'error': 'Forbidden in production'}, status=403)

    order_id = request.POST.get('order_id', '').strip()
    payment = UzumPayment.objects.filter(order_number=order_id).first()
    if not payment:
        return JsonResponse({'error': 'Payment not found'}, status=404)

    # Trigger internal webhook logic with test signature
    from django.test import RequestFactory
    rf = RequestFactory()
    body = json.dumps({
        'orderNumber': payment.order_number,
        'orderId': payment.uzum_order_id or f"uzum_mock_{payment.order_number}",
        'status': 'COMPLETED',
        'amount': int(payment.amount_uzs * 100)
    })
    req = rf.post(
        '/payments/uzum/webhook/',
        data=body,
        content_type='application/json',
        HTTP_X_SIGNATURE='test_signature'
    )
    return uzum_webhook(req)
