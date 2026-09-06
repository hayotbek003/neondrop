import logging
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_http_methods
from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib import messages
from django.http import JsonResponse
from django.conf import settings
from decimal import Decimal

from .forms import RegistrationForm, LoginForm, ProfileSettingsForm
from .models import Profile
from cases.models import Opening
from payments.services import modify_user_balance
from config.security import rate_limit, get_client_ip

security_logger = logging.getLogger('neondrop.security')
audit_logger = logging.getLogger('neondrop.audit')

@ensure_csrf_cookie
@rate_limit(key_prefix='register', limit=10, period=60, by_user=False, methods=('POST',))
@require_http_methods(["GET", "POST"])
def register_view(request):
    if request.user.is_authenticated:
        return redirect('cases:home')
        
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            user.save()
            
            # Update profile telegram username if provided
            tg = form.cleaned_data.get('telegram_username')
            if tg:
                user.profile.telegram_username = tg.strip()
                user.profile.save()
                
            # Log audit
            ip = get_client_ip(request)
            audit_logger.info(f"USER_REGISTRATION: username={user.username}, id={user.id}, email={user.email}, ip={ip}")
            
            login(request, user)
            request.session.set_expiry(getattr(settings, 'SESSION_COOKIE_AGE', 2592000))
            
            messages.success(request, f"Добро пожаловать в NEONDROP, {user.username}! Вам начислен приветственный баланс $100.00.")
            return redirect('cases:home')
        else:
            ip = get_client_ip(request)
            security_logger.warning(f"Registration validation failed from IP {ip}: {form.errors.as_json()}")
    else:
        form = RegistrationForm()
        
    return render(request, 'register.html', {'form': form})

@ensure_csrf_cookie
@rate_limit(key_prefix='login', limit=10, period=60, by_user=False, methods=('POST',))
@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect('cases:home')
        
    if request.method == 'POST':
        form = LoginForm(request.POST, request=request)
        ip = get_client_ip(request)
        if form.is_valid():
            user = form.user
            login(request, user)
            request.session.set_expiry(getattr(settings, 'SESSION_COOKIE_AGE', 2592000))
            
            audit_logger.info(f"USER_LOGIN_SUCCESS: username={user.username}, id={user.id}, ip={ip}")
            messages.success(request, f"С возвращением, {user.username}!")
            next_url = request.GET.get('next', 'cases:home')
            return redirect(next_url)
        else:
            security_logger.warning(f"USER_LOGIN_FAILED: ip={ip}")
    else:
        form = LoginForm(request=request)
        
    return render(request, 'login.html', {'form': form})

@require_http_methods(["GET", "POST"])
def logout_view(request):
    if request.user.is_authenticated:
        audit_logger.info(f"USER_LOGOUT: username={request.user.username}, id={request.user.id}, ip={get_client_ip(request)}")
    logout(request)
    messages.info(request, "Вы успешно вышли из аккаунта.")
    return redirect('cases:home')

@ensure_csrf_cookie
@login_required
def profile_view(request):
    profile = request.user.profile
    recent_openings = Opening.objects.filter(user=request.user).select_related('case', 'item')[:10]
    total_inventory_items = request.user.inventory_items.filter(is_sold=False).count()
    
    from django.utils import timezone
    from cases.models import PersonalCaseChance, UserFreeOpening, PromoCodeUse
    now = timezone.now()
    
    active_promotions = PersonalCaseChance.objects.filter(
        user=request.user,
        is_active=True,
        starts_at__lte=now,
        expires_at__gte=now
    ).select_related('case', 'item')

    free_openings = UserFreeOpening.objects.filter(
        user=request.user,
        openings_left__gt=0
    ).select_related('case')

    used_promocodes = PromoCodeUse.objects.filter(
        user=request.user
    ).select_related('promo_code').order_by('-used_at')[:10]
    
    context = {
        'profile': profile,
        'recent_openings': recent_openings,
        'total_inventory_items': total_inventory_items,
        'active_promotions': active_promotions,
        'free_openings': free_openings,
        'used_promocodes': used_promocodes,
        'active_tab': 'profile',
    }
    return render(request, 'profile.html', context)

@login_required
def history_view(request):
    profile = request.user.profile
    openings = Opening.objects.filter(user=request.user).select_related('case', 'item').order_by('-created_at')
    
    context = {
        'profile': profile,
        'openings': openings,
        'active_tab': 'history',
    }
    return render(request, 'history.html', context)

@login_required
def settings_view(request):
    profile = request.user.profile
    if request.method == 'POST':
        form = ProfileSettingsForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            audit_logger.info(f"PROFILE_SETTINGS_UPDATE: user={request.user.username}, ip={get_client_ip(request)}")
            messages.success(request, "Настройки профиля сохранены.")
            return redirect('users:profile')
    else:
        form = ProfileSettingsForm(instance=profile)
        
    return render(request, 'profile.html', {
        'profile': profile,
        'form': form,
        'active_tab': 'settings',
    })

@login_required
def api_user_balance(request):
    """Secure endpoint returning live balance directly from the locked database record."""
    profile = Profile.objects.filter(user=request.user).first()
    if not profile:
        return JsonResponse({'success': False, 'error': 'Профиль не найден.'}, status=404)
        
    return JsonResponse({
        'success': True,
        'balance': float(profile.balance),
        'username': request.user.username,
    })
