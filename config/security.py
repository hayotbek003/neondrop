import functools
import logging
import hashlib
from typing import Optional, Callable, Sequence
from django.core.cache import cache
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.core.exceptions import ValidationError
from PIL import Image

security_logger = logging.getLogger('neondrop.security')
audit_logger = logging.getLogger('neondrop.audit')

def get_client_ip(request) -> str:
    """Extract client IP address safely from request headers."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
    return ip

def rate_limit(key_prefix: str, limit: int, period: int = 60, by_user: bool = True, methods: Optional[Sequence[str]] = None):
    """
    Rate limiting decorator using Django Cache.
    :param key_prefix: Unique action identifier (e.g. 'login', 'open_case')
    :param limit: Maximum allowed requests within the period
    :param period: Time window in seconds
    :param by_user: If True and request.user is authenticated, uses user ID; otherwise IP.
    :param methods: If provided, only requests with these HTTP methods are rate-limited (e.g. ('POST',)).
    """
    def decorator(view_func: Callable):
        @functools.wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if methods and request.method not in methods:
                return view_func(request, *args, **kwargs)

            ip = get_client_ip(request)
            if by_user and request.user.is_authenticated:
                identifier = f"user:{request.user.id}"
            else:
                identifier = f"ip:{ip}"

            cache_key = f"ratelimit:{key_prefix}:{identifier}"
            
            try:
                current_requests = cache.get(cache_key, 0)
                if current_requests >= limit:
                    security_logger.warning(
                        f"Rate limit exceeded: action={key_prefix}, identifier={identifier}, "
                        f"limit={limit}/{period}s, path={request.path}"
                    )
                    
                    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.path.startswith('/api/') or request.path.endswith('/open/'):
                        response = JsonResponse({
                            'success': False,
                            'error': 'Слишком много запросов. Пожалуйста, подождите немного перед повторной попыткой.'
                        }, status=429)
                        response['Retry-After'] = str(period)
                        return response
                    
                    # HTML response for browser forms
                    return render(request, '429.html', {'retry_after': period}, status=429)
                
                # Increment request count
                if current_requests == 0:
                    cache.set(cache_key, 1, timeout=period)
                else:
                    try:
                        cache.incr(cache_key)
                    except ValueError:
                        cache.set(cache_key, current_requests + 1, timeout=period)
            except Exception as e:
                # Fail-open if cache is temporarily unavailable, but log it
                security_logger.error(f"Rate limiting cache error: {e}")

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator

def check_and_store_idempotency_key(user_id: int, key: Optional[str], action: str, timeout: int = 60) -> bool:
    """
    Atomic check for duplicate/simultaneous request prevention.
    Returns True if the request is unique and accepted, False if it's a duplicate.
    """
    if not key:
        return True  # If client didn't supply key, rely on DB row-level locking

    sanitized_key = hashlib.sha256(f"{user_id}:{action}:{key}".encode('utf-8')).hexdigest()
    cache_key = f"idempotency:{sanitized_key}"
    
    # cache.add only sets if key does not exist; returns True if key was set, False if existed
    is_unique = cache.add(cache_key, 'PROCESSING', timeout=timeout)
    if not is_unique:
        security_logger.warning(f"Duplicate request detected for user {user_id}, action {action}, key {key}")
        return False
    return True

def validate_uploaded_image(file_obj, max_size_mb: int = 2) -> None:
    """
    Validates uploaded image file:
    - Maximum file size
    - Allowed extension
    - Valid image header via Pillow
    """
    if not file_obj:
        return

    # 1. File size check
    max_bytes = max_size_mb * 1024 * 1024
    if file_obj.size > max_bytes:
        raise ValidationError(f"Размер файла не должен превышать {max_size_mb} МБ.")

    # 2. Extension check
    allowed_extensions = ['jpg', 'jpeg', 'png', 'webp']
    file_ext = file_obj.name.split('.')[-1].lower() if '.' in file_obj.name else ''
    if file_ext not in allowed_extensions:
        raise ValidationError("Поддерживаются только изображения форматов JPG, PNG и WEBP.")

    # 3. Content inspection via Pillow
    try:
        file_obj.seek(0)
        img = Image.open(file_obj)
        img.verify()
        file_obj.seek(0)
    except Exception:
        raise ValidationError("Загруженный файл поврежден или не является корректным изображением.")
