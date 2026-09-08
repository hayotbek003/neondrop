from decimal import Decimal
from datetime import timedelta
from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.contrib.auth.models import User

from cases.models import Case, Item, CaseItem, Opening, PromoCode
from inventory.models import InventoryItem
from payments.models import Transaction


def get_dashboard_context(request):
    """
    Computes real-time KPIs and activity feeds for the NEONDROP Cyber Admin Dashboard.
    """
    now = timezone.now()
    thirty_days_ago = now - timedelta(days=30)

    # 1. User metrics
    total_users = User.objects.count()
    active_users = User.objects.filter(
        Q(last_login__gte=thirty_days_ago) | Q(openings__isnull=False)
    ).distinct().count()

    # 2. Cases & Items catalog
    total_cases = Case.objects.count()
    active_cases = Case.objects.filter(active=True).count()
    total_items = Item.objects.count()

    # 3. Openings & Turnover
    total_openings = Opening.objects.count()
    turnover_agg = Opening.objects.aggregate(s=Sum('price'))
    total_turnover = turnover_agg['s'] or Decimal('0.00')

    # 4. Deposits
    dep_agg = Transaction.objects.filter(transaction_type='deposit', status='completed').aggregate(
        total=Sum('amount'), count=Count('id')
    )
    total_deposits_sum = dep_agg['total'] or Decimal('0.00')
    total_deposits_count = dep_agg['count'] or 0

    # 5. Withdrawals
    with_agg = Transaction.objects.filter(
        transaction_type__icontains='withdraw', status='completed'
    ).aggregate(
        total=Sum('amount'), count=Count('id')
    )
    total_withdrawals_sum = abs(with_agg['total'] or Decimal('0.00'))
    total_withdrawals_count = with_agg['count'] or 0

    # 6. Pending requests (deposits and withdrawals)
    pending_transactions = Transaction.objects.filter(status='pending').select_related('user').order_by('-created_at')
    pending_count = pending_transactions.count()

    # 7. Promo codes & Blogger metrics
    total_promocodes = PromoCode.objects.count()
    blogger_promos = PromoCode.objects.filter(blogger_percentage__gt=0)
    
    total_blogger_loss = Decimal('0.00')
    total_blogger_payout = Decimal('0.00')
    total_site_revenue = Decimal('0.00')
    
    blogger_stats_list = []
    for bp in blogger_promos[:10]:
        stats = bp.get_stats_all_time()
        loss = stats.get('net_loss', Decimal('0.00'))
        payout = stats.get('blogger_payout', Decimal('0.00'))
        revenue = stats.get('site_revenue', Decimal('0.00'))
        total_blogger_loss += loss
        total_blogger_payout += payout
        total_site_revenue += revenue
        blogger_stats_list.append({
            'code': bp.code,
            'blogger_name': bp.blogger_name or bp.code,
            'percentage': bp.blogger_percentage,
            'uses_count': bp.uses.count(),
            'net_loss': loss,
            'payout': payout,
            'site_revenue': revenue,
        })

    # 8. Live activity feeds
    recent_openings = Opening.objects.select_related('user', 'case', 'item').order_by('-created_at')[:8]

    return {
        'kpi_total_users': total_users,
        'kpi_active_users': active_users,
        'kpi_cases_count': total_cases,
        'kpi_active_cases': active_cases,
        'kpi_items_count': total_items,
        'kpi_openings_count': total_openings,
        'kpi_total_turnover': total_turnover,
        'kpi_deposits_sum': total_deposits_sum,
        'kpi_deposits_count': total_deposits_count,
        'kpi_withdrawals_sum': total_withdrawals_sum,
        'kpi_withdrawals_count': total_withdrawals_count,
        'kpi_pending_count': pending_count,
        'kpi_promocodes_count': total_promocodes,
        'kpi_blogger_payout': total_blogger_payout,
        'kpi_site_revenue': total_site_revenue,
        'recent_openings': recent_openings,
        'pending_transactions': pending_transactions[:8],
        'blogger_stats_list': blogger_stats_list,
    }
