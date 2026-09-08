import os
import re
import secrets
import logging
import urllib.parse
from decimal import Decimal
import requests
from django.conf import settings
from django.urls import reverse
from django.contrib.auth.models import User
from django.db import transaction
from .models import GoogleAccount, Profile

logger = logging.getLogger('neondrop.security')
audit_logger = logging.getLogger('neondrop.audit')

GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URL = 'https://www.googleapis.com/oauth2/v3/userinfo'


class GoogleOAuthError(Exception):
    """Custom exception raised for Google OAuth flow errors."""
    pass


def get_google_client_id():
    """Returns Google Client ID from environment or settings."""
    val = (
        os.environ.get('GOOGLE_CLIENT_ID')
        or os.environ.get('GOOGLE_OAUTH_CLIENT_ID')
        or os.environ.get('GOOGLE_CLIENTID')
        or getattr(settings, 'GOOGLE_CLIENT_ID', '')
    )
    if not val:
        for k, v in os.environ.items():
            if k.strip().upper() in ('GOOGLE_CLIENT_ID', 'GOOGLE_OAUTH_CLIENT_ID', 'GOOGLE_CLIENTID'):
                val = v
                break
    return str(val or '').strip().strip('"\'')


def get_google_client_secret():
    """Returns Google Client Secret from environment or settings."""
    val = (
        os.environ.get('GOOGLE_CLIENT_SECRET')
        or os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET')
        or os.environ.get('GOOGLE_CLIENTSECRET')
        or getattr(settings, 'GOOGLE_CLIENT_SECRET', '')
    )
    if not val:
        for k, v in os.environ.items():
            if k.strip().upper() in ('GOOGLE_CLIENT_SECRET', 'GOOGLE_OAUTH_CLIENT_SECRET', 'GOOGLE_CLIENTSECRET'):
                val = v
                break
    return str(val or '').strip().strip('"\'')


def is_google_oauth_configured():
    """Checks whether both GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are provided."""
    client_id = get_google_client_id()
    client_secret = get_google_client_secret()
    has_both = bool(client_id and client_secret)
    if not has_both:
        logger.info(
            f"Google OAuth configuration status: client_id_present={bool(client_id)}, "
            f"client_secret_present={bool(client_secret)}"
        )
    return has_both


def get_google_redirect_uri(request):
    """
    Computes the authoritative Google OAuth Redirect URI.
    Supports explicit GOOGLE_OAUTH_REDIRECT_URI environment variable,
    and dynamically builds the absolute URI for localhost or production HTTPS.
    """
    env_redirect = os.environ.get('GOOGLE_OAUTH_REDIRECT_URI', '').strip()
    if env_redirect:
        return env_redirect

    uri = request.build_absolute_uri(reverse('users:google_callback'))
    # Ensure https in production or behind reverse proxies
    if not settings.DEBUG and uri.startswith('http://'):
        uri = 'https://' + uri[7:]
    elif request.headers.get('x-forwarded-proto') == 'https' and uri.startswith('http://'):
        uri = 'https://' + uri[7:]

    return uri


def build_google_auth_url(request, state, redirect_uri):
    """
    Builds the Google OAuth 2.0 authorization URL with required scopes.
    """
    client_id = get_google_client_id()
    if not client_id:
        raise GoogleOAuthError("GOOGLE_CLIENT_ID is not configured in environment variables.")

    params = {
        'client_id': client_id,
        'response_type': 'code',
        'scope': 'openid email profile',
        'redirect_uri': redirect_uri,
        'state': state,
        'access_type': 'online',
        'prompt': 'select_account',
    }
    return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"


def exchange_code_for_tokens(code, redirect_uri):
    """
    Exchanges the authorization code for Google access token and id_token.
    """
    client_id = get_google_client_id()
    client_secret = get_google_client_secret()

    if not client_id or not client_secret:
        raise GoogleOAuthError("Google OAuth credentials are not fully configured.")

    payload = {
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code',
    }

    try:
        response = requests.post(GOOGLE_TOKEN_URL, data=payload, timeout=12)
    except requests.RequestException as e:
        logger.error(f"Google OAuth token exchange network error: {e}")
        raise GoogleOAuthError("Не удалось связаться с сервером авторизации Google. Повторите попытку.")

    if response.status_code != 200:
        logger.warning(f"Google OAuth token exchange failed with status {response.status_code}: {response.text}")
        raise GoogleOAuthError("Ошибка проверки кода авторизации Google. Возможно, код устарел.")

    data = response.json()
    access_token = data.get('access_token')
    if not access_token:
        raise GoogleOAuthError("От Google не получен токен доступа.")

    return data


def fetch_google_user_info(access_token):
    """
    Fetches the verified user profile information from Google userinfo endpoint.
    """
    headers = {'Authorization': f'Bearer {access_token}'}

    try:
        response = requests.get(GOOGLE_USERINFO_URL, headers=headers, timeout=12)
    except requests.RequestException as e:
        logger.error(f"Google userinfo request network error: {e}")
        raise GoogleOAuthError("Не удалось получить данные профиля от Google.")

    if response.status_code != 200:
        logger.warning(f"Google userinfo failed with status {response.status_code}: {response.text}")
        raise GoogleOAuthError("Ошибка получения профиля от Google.")

    info = response.json()
    sub = info.get('sub')
    email = info.get('email')

    if not sub or not email:
        raise GoogleOAuthError("Google не предоставил обязательные данные (email или Google ID).")

    return info


def generate_unique_username(base_name, email):
    """
    Generates a clean, unique username based on the Google user's name or email prefix.
    """
    cleaned = re.sub(r'[^\w.@+-]', '', (base_name or '').replace(' ', '_'))
    if not cleaned:
        cleaned = email.split('@')[0]
    cleaned = re.sub(r'[^\w.@+-]', '', cleaned)[:24] or 'google_user'

    candidate = cleaned
    counter = 1
    while User.objects.filter(username__iexact=candidate).exists():
        suffix = f"_{counter}"
        candidate = f"{cleaned[:24 - len(suffix)]}{suffix}"
        counter += 1

    return candidate


@transaction.atomic
def get_or_create_google_user(google_info):
    """
    Idempotently resolves or creates a Django User linked to a Google account.
    - If GoogleAccount with google_id exists: returns associated User.
    - If User with email exists: links GoogleAccount to that User without altering their password or data.
    - If new: creates User with unusable password, creates Profile, and links GoogleAccount.
    """
    google_id = str(google_info.get('sub', '')).strip()
    raw_email = str(google_info.get('email', '')).strip()
    email = raw_email.lower()
    name = str(google_info.get('name', '')).strip()
    picture = str(google_info.get('picture', '')).strip()

    if not google_id or not email:
        raise GoogleOAuthError("Отсутствуют обязательные данные Google (sub/email).")

    # 1. Match by linked GoogleAccount
    existing_link = GoogleAccount.objects.select_related('user', 'user__profile').filter(google_id=google_id).first()
    if existing_link:
        user = existing_link.user
        # Update picture if profile doesn't have custom avatar
        if picture and hasattr(user, 'profile') and not user.profile.avatar and not user.profile.avatar_url:
            user.profile.avatar_url = picture
            user.profile.save(update_fields=['avatar_url'])
        return user, False

    # 2. Match by email (case-insensitive) - prevent duplicate accounts!
    existing_user = User.objects.select_related('profile').filter(email__iexact=email).first()
    if existing_user:
        # Link Google account to this existing user
        GoogleAccount.objects.get_or_create(
            user=existing_user,
            defaults={'google_id': google_id, 'email': email}
        )
        if picture and hasattr(existing_user, 'profile') and not existing_user.profile.avatar and not existing_user.profile.avatar_url:
            existing_user.profile.avatar_url = picture
            existing_user.profile.save(update_fields=['avatar_url'])
        audit_logger.info(f"GOOGLE_ACCOUNT_LINKED: user={existing_user.username} (id={existing_user.id}) linked to google_id={google_id}")
        return existing_user, False

    # 3. Create a brand new user
    username = generate_unique_username(name, email)
    new_user = User.objects.create_user(
        username=username,
        email=email
    )
    new_user.set_unusable_password()  # Google passwords are never handled or stored!
    new_user.save()

    # Ensure profile created and set avatar_url if provided
    profile, _ = Profile.objects.get_or_create(user=new_user)
    if picture:
        profile.avatar_url = picture
        profile.save(update_fields=['avatar_url'])
    new_user.profile = profile

    # Create link
    GoogleAccount.objects.create(
        user=new_user,
        google_id=google_id,
        email=email
    )

    audit_logger.info(f"GOOGLE_ACCOUNT_REGISTERED: user={new_user.username} (id={new_user.id}), google_id={google_id}, email={email}")
    return new_user, True
