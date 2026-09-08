from decimal import Decimal
from .models import Profile
from payments.currency import get_currency_rates, uc_to_usd, format_uc, format_usd_approx

from django.conf import settings
from django.templatetags.static import static

def user_profile_context(request):
    """
    Context processor to inject profile, balance, and system currency stats into templates.
    """
    rates = get_currency_rates()
    context = {
        'user_profile': None,
        'user_balance': Decimal('0.00'),
        'user_balance_usd': Decimal('0.00'),
        'uc_icon_url': static('images/uc_icon.png'),
        'currency_rates': {
            'uc_to_uzs': float(rates['uc_to_uzs']),
            'usd_to_uzs': float(rates['usd_to_uzs']),
            'uc_to_usd_rate': float(rates['uc_to_usd_rate']),
        },
        'db_is_persistent': getattr(settings, 'IS_PERSISTENT_DATABASE', False),
        'db_engine_name': getattr(settings, 'DATABASE_ENGINE_NAME', 'SQLite'),
        'db_host_display': getattr(settings, 'DATABASE_HOST_DISPLAY', 'Local'),
    }
    if request.user.is_authenticated:
        profile, _ = Profile.objects.get_or_create(user=request.user)
        context['user_profile'] = profile
        context['user_balance'] = profile.balance
        context['user_balance_usd'] = uc_to_usd(profile.balance)
    return context
