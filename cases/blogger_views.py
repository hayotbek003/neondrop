import csv
from datetime import datetime, timedelta
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_POST
from django.http import HttpResponse, HttpResponseForbidden
from django.utils import timezone
from django.db import transaction

from .models import PromoCode, BloggerPayout, PromoCodeUse, Opening
from payments.models import Transaction


def parse_date_filters(request):
    """
    Parses request GET parameters for date presets and returns:
    (date_from, date_to, period_slug, period_title, date_from_str, date_to_str)
    """
    period = request.GET.get('period', 'all').strip()
    date_from_str = request.GET.get('date_from', '').strip()
    date_to_str = request.GET.get('date_to', '').strip()

    now = timezone.now()
    date_from = None
    date_to = None
    period_title = "За всё время"

    if period == 'today':
        date_from = now.replace(hour=0, minute=0, second=0, microsecond=0)
        date_to = now
        period_title = "Сегодня"
    elif period == 'yesterday':
        start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        date_from = start_today - timedelta(days=1)
        date_to = start_today - timedelta(microseconds=1)
        period_title = "Вчера"
    elif period == '7d':
        date_from = now - timedelta(days=7)
        date_to = now
        period_title = "За 7 дней"
    elif period == '30d':
        date_from = now - timedelta(days=30)
        date_to = now
        period_title = "За 30 дней"
    elif period == 'this_month':
        date_from = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        date_to = now
        period_title = "Этот месяц"
    elif period == 'prev_month':
        start_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        date_to = start_this_month - timedelta(microseconds=1)
        date_from = date_to.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        period_title = "Прошлый месяц"
    elif period == 'custom' or (date_from_str and date_to_str):
        period = 'custom'
        try:
            if date_from_str:
                d_from = datetime.strptime(date_from_str, '%Y-%m-%d')
                date_from = timezone.make_aware(d_from.replace(hour=0, minute=0, second=0))
            if date_to_str:
                d_to = datetime.strptime(date_to_str, '%Y-%m-%d')
                date_to = timezone.make_aware(d_to.replace(hour=23, minute=59, second=59, microsecond=999999))
            period_title = f"{date_from_str} — {date_to_str}"
        except Exception:
            date_from = None
            date_to = None
            period_title = "За всё время"

    return date_from, date_to, period, period_title, date_from_str, date_to_str


from users.models import has_admin_perm


@staff_member_required
def blogger_dashboard_view(request):
    """
    Main Cyberpunk Admin Blogger Dashboard view:
    - Overview KPIs
    - Blogger summary table with live calculated Net Loss, Deposits, Payouts, Remaining
    - Monthly breakdown with payout modal
    - Payout history
    """
    if not has_admin_perm(request.user, 'can_view_blogger_stats'):
        return HttpResponseForbidden("⛔ Ошибка доступа: у вас нет прав на просмотр аналитики блогеров (can_view_blogger_stats).")

    date_from, date_to, period, period_title, date_from_str, date_to_str = parse_date_filters(request)

    promo_codes = PromoCode.objects.all().order_by('code')

    blogger_rows = []
    total_users_count = 0
    total_deposits_all = Decimal('0.00')
    total_spent_all = Decimal('0.00')
    total_won_all = Decimal('0.00')
    total_net_loss_all = Decimal('0.00')
    total_payout_calculated_all = Decimal('0.00')
    total_payout_recorded_all = Decimal('0.00')
    total_remaining_all = Decimal('0.00')

    # Gather payouts made
    payouts_qs = BloggerPayout.objects.all().select_related('promo_code', 'admin_user')

    # Calculate statistics per promo code
    for pc in promo_codes:
        stats = pc.get_stats_for_period(date_from=date_from, date_to=date_to)
        
        # Payouts recorded for this promo code
        pc_payouts_qs = payouts_qs.filter(promo_code=pc)
        if date_from:
            pc_payouts_qs = pc_payouts_qs.filter(created_at__gte=date_from)
        if date_to:
            pc_payouts_qs = pc_payouts_qs.filter(created_at__lte=date_to)

        paid_amount = sum((p.amount for p in pc_payouts_qs), Decimal('0.00'))
        remaining_balance = max(Decimal('0.00'), stats['blogger_payout'] - paid_amount)

        # Monthly breakdown for this promo code
        monthly_breakdown = pc.get_monthly_breakdown()

        blogger_name = pc.blogger_name or pc.code
        row = {
            'promo_code': pc,
            'blogger_name': blogger_name,
            'code': pc.code,
            'percentage': stats['blogger_percentage'],
            'users_count': stats['users_count'],
            'total_deposits': stats['total_deposits'],
            'total_spent': stats['total_spent'],
            'total_won': stats['total_won'],
            'net_loss': stats['net_loss'],
            'blogger_payout': stats['blogger_payout'],
            'paid_amount': paid_amount,
            'remaining_balance': remaining_balance,
            'monthly_breakdown': monthly_breakdown,
        }
        blogger_rows.append(row)

        total_users_count += stats['users_count']
        total_deposits_all += stats['total_deposits']
        total_spent_all += stats['total_spent']
        total_won_all += stats['total_won']
        total_net_loss_all += stats['net_loss']
        total_payout_calculated_all += stats['blogger_payout']
        total_payout_recorded_all += paid_amount
        total_remaining_all += remaining_balance

    # Recent payouts history (last 50)
    recent_payouts = payouts_qs.order_by('-created_at')[:50]

    # Current month key (e.g. "2026-09")
    current_month_key = timezone.now().strftime('%Y-%m')

    context = {
        'title': '📊 Статистика и выплаты блогерам',
        'is_superuser': request.user.is_superuser,
        'period': period,
        'period_title': period_title,
        'date_from_str': date_from_str,
        'date_to_str': date_to_str,
        'blogger_rows': blogger_rows,
        'total_bloggers': len(blogger_rows),
        'total_users_count': total_users_count,
        'total_deposits_all': total_deposits_all,
        'total_spent_all': total_spent_all,
        'total_won_all': total_won_all,
        'total_net_loss_all': total_net_loss_all,
        'total_payout_calculated_all': total_payout_calculated_all,
        'total_payout_recorded_all': total_payout_recorded_all,
        'total_remaining_all': total_remaining_all,
        'recent_payouts': recent_payouts,
        'current_month_key': current_month_key,
    }

    return render(request, 'admin/blogger_dashboard.html', context)


@staff_member_required
@require_POST
def mark_blogger_payout_view(request):
    """
    Superuser-only action to record a payout to a blogger for a specific period.
    """
    if not request.user.is_superuser:
        messages.error(request, "Только главный администратор может отмечать выплаты блогерам.")
        return HttpResponseForbidden("Forbidden: Superuser access required.")

    promo_code_id = request.POST.get('promo_code_id')
    amount_raw = request.POST.get('amount', '').strip().replace(',', '.')
    period = request.POST.get('period', '').strip()
    comment = request.POST.get('comment', '').strip()

    promo_code = get_object_or_404(PromoCode, id=promo_code_id)

    try:
        amount = Decimal(amount_raw)
        if amount <= Decimal('0.00'):
            raise ValueError("Сумма выплаты должна быть больше 0.")
    except Exception as e:
        messages.error(request, f"Некорректная сумма выплаты: {e}")
        return redirect('admin_blogger_dashboard')

    if not period:
        period = timezone.now().strftime('%Y-%m')

    with transaction.atomic():
        payout = BloggerPayout.objects.create(
            promo_code=promo_code,
            amount=amount,
            period=period,
            admin_user=request.user,
            comment=comment
        )

    blogger_label = promo_code.blogger_name or promo_code.code
    messages.success(
        request,
        f"✅ Выплата {amount:,.2f} UC для блогера {blogger_label} (период: {period}) успешно зафиксирована!"
    )
    return redirect('admin_blogger_dashboard')


@staff_member_required
def export_blogger_stats_csv_view(request):
    """
    Exports a comprehensive CSV report matching all requirements:
    Блогер, Промокод, Период, Пользователи, Пополнения, Расходы на кейсы,
    Стоимость выпавших предметов, Net Loss, Процент, Начисление, Выплачено, Остаток.
    """
    if not has_admin_perm(request.user, 'can_view_blogger_stats'):
        return HttpResponseForbidden("⛔ Ошибка доступа: у вас нет прав на экспорт статистики блогеров (can_view_blogger_stats).")
    date_from, date_to, period, period_title, _, _ = parse_date_filters(request)
    promo_codes = PromoCode.objects.all().order_by('code')

    filename = f"neondrop_blogger_stats_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.csv"
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    # UTF-8 BOM for Excel compatibility
    response.write('\ufeff'.encode('utf-8'))

    writer = csv.writer(response)
    writer.writerow([
        'Блогер',
        'Промокод',
        'Период',
        'Пользователи',
        'Пополнения (UC)',
        'Расходы на кейсы (UC)',
        'Стоимость выпавших предметов (UC)',
        'Net Loss (UC)',
        'Процент (%)',
        'К выплате (UC)',
        'Выплачено (UC)',
        'Остаток (UC)',
    ])

    for pc in promo_codes:
        stats = pc.get_stats_for_period(date_from=date_from, date_to=date_to)
        
        pc_payouts_qs = pc.payouts.all()
        if date_from:
            pc_payouts_qs = pc_payouts_qs.filter(created_at__gte=date_from)
        if date_to:
            pc_payouts_qs = pc_payouts_qs.filter(created_at__lte=date_to)

        paid_amount = sum((p.amount for p in pc_payouts_qs), Decimal('0.00'))
        remaining = max(Decimal('0.00'), stats['blogger_payout'] - paid_amount)

        writer.writerow([
            pc.blogger_name or pc.code,
            pc.code,
            period_title,
            stats['users_count'],
            f"{stats['total_deposits']:.2f}",
            f"{stats['total_spent']:.2f}",
            f"{stats['total_won']:.2f}",
            f"{stats['net_loss']:.2f}",
            f"{stats['blogger_percentage']}%",
            f"{stats['blogger_payout']:.2f}",
            f"{paid_amount:.2f}",
            f"{remaining:.2f}",
        ])

    return response
