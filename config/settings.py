import os
from pathlib import Path
from decimal import Decimal

# Try to load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Quick-start development settings - unsuitable for production
SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'django-insecure-neondrop-cyberpunk-case-opening-secret-key-prod-change-me-2026'
)

# DEBUG configuration
DEBUG = os.environ.get('DJANGO_DEBUG', 'True').lower() in ('true', '1', 'yes')

# Proxy SSL Header Configuration (CRITICAL for Render, Heroku, AWS, Cloudflare, etc.)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True

# ALLOWED_HOSTS configuration
allowed_hosts_raw = os.environ.get('DJANGO_ALLOWED_HOSTS', '*')
if allowed_hosts_raw == '*':
    ALLOWED_HOSTS = ['*']
else:
    ALLOWED_HOSTS = [h.strip() for h in allowed_hosts_raw.split(',') if h.strip()]
    for default_host in ['neondrop-ujly.onrender.com', '.onrender.com', 'localhost', '127.0.0.1', 'testserver']:
        if default_host not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(default_host)

# CSRF Trusted Origins Configuration
csrf_origins_env = os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS = [
    'https://neondrop-ujly.onrender.com',
    'https://*.onrender.com',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'http://localhost',
    'http://127.0.0.1',
]
if csrf_origins_env:
    for origin in csrf_origins_env.split(','):
        origin = origin.strip()
        if origin:
            if not origin.startswith(('http://', 'https://')):
                origin = f'https://{origin}'
            origin = origin.rstrip('/')
            if origin not in CSRF_TRUSTED_ORIGINS:
                CSRF_TRUSTED_ORIGINS.append(origin)

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    
    # Custom NEONDROP Apps
    'users.apps.UsersConfig',
    'cases.apps.CasesConfig',
    'inventory.apps.InventoryConfig',
    'payments.apps.PaymentsConfig',
    'upgrades.apps.UpgradesConfig',
    'contracts.apps.ContractsConfig',
    'battles.apps.BattlesConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'users.context_processors.user_profile_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database configuration
# Persistent PostgreSQL database is configured via DATABASE_URL on Render / Production.
# When DATABASE_URL is configured, all cases, items, users, and transactions persist across all deploys.
database_url = os.environ.get('DATABASE_URL', '').strip()
if database_url:
    import urllib.parse
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)

    parsed_db = urllib.parse.urlparse(database_url)
    db_engine = 'django.db.backends.postgresql'
    if 'sqlite' in parsed_db.scheme:
        db_engine = 'django.db.backends.sqlite3'

    db_config = {
        'ENGINE': db_engine,
        'NAME': urllib.parse.unquote(parsed_db.path.lstrip('/')),
        'USER': urllib.parse.unquote(parsed_db.username or ''),
        'PASSWORD': urllib.parse.unquote(parsed_db.password or ''),
        'HOST': parsed_db.hostname or '',
        'PORT': parsed_db.port or '',
        'CONN_MAX_AGE': 600,
        'CONN_HEALTH_CHECKS': True,
    }

    query_params = urllib.parse.parse_qs(parsed_db.query)
    options = {}
    if 'sslmode' in query_params:
        options['sslmode'] = query_params['sslmode'][0]
    elif parsed_db.hostname and parsed_db.hostname not in ('localhost', '127.0.0.1'):
        options['sslmode'] = os.environ.get('DB_SSLMODE', 'prefer')

    if options:
        db_config['OPTIONS'] = options

    DATABASES = {
        'default': db_config
    }
else:
    # DATABASE_URL is not set — use SQLite fallback.
    # On Render: DATABASE_URL is injected at runtime via render.yaml (fromDatabase).
    # During build phase (collectstatic etc.) DATABASE_URL is not yet available,
    # so SQLite fallback is used temporarily for build-time commands only.
    # At runtime, DATABASE_URL will always be present (from neondrop-db PostgreSQL).
    sqlite_file = BASE_DIR / 'db.sqlite3'
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': sqlite_file,
            'OPTIONS': {
                'timeout': 20,
            },
        }
    }


# Cache & Rate Limiting Configuration
REDIS_URL = os.environ.get('REDIS_URL', '').strip()
if REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'neondrop-local-cache',
        }
    }

# Authentication Backends
AUTHENTICATION_BACKENDS = [
    'users.backends.CaseInsensitiveModelBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 8},
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static & Media files
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
(MEDIA_ROOT / 'cases').mkdir(parents=True, exist_ok=True)
(MEDIA_ROOT / 'items').mkdir(parents=True, exist_ok=True)
(MEDIA_ROOT / 'avatars').mkdir(parents=True, exist_ok=True)

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Authentication URLs
LOGIN_URL = 'users:login'
LOGIN_REDIRECT_URL = 'cases:home'
LOGOUT_REDIRECT_URL = 'cases:home'

# Session & Cookie Security
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_NAME = 'neondrop_sessionid'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_AGE = 2592000  # 30 days persistent session

CSRF_COOKIE_NAME = 'csrftoken'
CSRF_COOKIE_HTTPONLY = False  # Allows frontend JS getCookie('csrftoken') to read CSRF
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_AGE = 31449600  # 1 year

# Cookie security - active in production or when explicitly enabled
SESSION_COOKIE_SECURE = not DEBUG or os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() in ('true', '1')
CSRF_COOKIE_SECURE = not DEBUG or os.environ.get('CSRF_COOKIE_SECURE', 'False').lower() in ('true', '1')

# Cookie domains default to exact request host
CSRF_COOKIE_DOMAIN = None
SESSION_COOKIE_DOMAIN = None

# Custom CSRF Failure View
CSRF_FAILURE_VIEW = 'cases.views.custom_csrf_failure_view'

# Security Headers
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

SECURE_SSL_REDIRECT = not DEBUG and os.environ.get('SECURE_SSL_REDIRECT', 'True').lower() in ('true', '1')

if not DEBUG:
    SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', '31536000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# Telegram Administrator Integration
TELEGRAM_BOT_USERNAME = os.environ.get('neondrop_admin', 'neondrop_admin').lstrip('@')

# Logging & Audit Configuration
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '[%(asctime)s] %(levelname)s in %(name)s: %(message)s'
        },
        'audit': {
            'format': '[%(asctime)s] [AUDIT] %(message)s'
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
        },
        'security_file': {
            'level': 'WARNING',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'security.log',
            'maxBytes': 1024 * 1024 * 10,  # 10 MB
            'backupCount': 5,
            'formatter': 'standard',
        },
        'audit_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'audit.log',
            'maxBytes': 1024 * 1024 * 10,  # 10 MB
            'backupCount': 10,
            'formatter': 'audit',
        },
    },
    'loggers': {
        'django.security': {
            'handlers': ['security_file', 'console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'neondrop.security': {
            'handlers': ['security_file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        'neondrop.audit': {
            'handlers': ['audit_file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
