from decimal import Decimal
from .models import Profile

def user_profile_context(request):
    """
    Context processor to inject profile, balance, and system stats into templates.
    """
    context = {
        'user_profile': None,
        'user_balance': Decimal('0.00'),
    }
    if request.user.is_authenticated:
        profile, _ = Profile.objects.get_or_create(user=request.user)
        context['user_profile'] = profile
        context['user_balance'] = profile.balance
    return context
