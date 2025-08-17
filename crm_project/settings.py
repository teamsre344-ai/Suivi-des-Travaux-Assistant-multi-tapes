import os
from pathlib import Path
from decouple import config
from django.core.management.utils import get_random_secret_key

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Core ---
SECRET_KEY = config('SECRET_KEY', default=get_random_secret_key())
DEBUG = config('DEBUG', cast=bool, default=True)

def _split(env_key: str, default_val: str = ''):
    return [x.strip() for x in config(env_key, default=default_val).split(',') if x.strip()]

ALLOWED_HOSTS = _split('ALLOWED_HOSTS', '127.0.0.1,localhost')
CSRF_TRUSTED_ORIGINS = _split('CSRF_TRUSTED_ORIGINS', 'http://127.0.0.1,http://localhost')

# --- Apps ---
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',  # intcomma, naturaltime, etc.
    'crm_app',
    'crispy_forms',
    'crispy_bootstrap5',
    'django.contrib.postgres',
]

CRISPY_ALLOWED_TEMPLATE_PACKS = 'bootstrap5'
CRISPY_TEMPLATE_PACK = 'bootstrap5'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'crm_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'crm_app' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'crm_project.wsgi.application'
ASGI_APPLICATION = 'crm_project.asgi.application'

# --- Database (Postgres via .env, else SQLite fallback) ---
ENGINE = config('DB_ENGINE', default='postgresql').lower()
if ENGINE == 'postgresql':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config('DB_NAME', default='crm_msui'),
            'USER': config('DB_USER', default='postgres'),
            'PASSWORD': config('DB_PASSWORD', default='postgres'),
            'HOST': config('DB_HOST', default='localhost'),
            'PORT': config('DB_PORT', default='5432'),
            'CONN_MAX_AGE': config('DB_CONN_MAX_AGE', cast=int, default=60),
            'OPTIONS': {
                # Example: set schema -> 'options': '-c search_path=public'
            },
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': str(BASE_DIR / config('DB_NAME', default='db.sqlite3')),
        }
    }

MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "/media/"


# --- I18N / TZ ---
LANGUAGE_CODE = 'fr-ca'
TIME_ZONE = 'America/Montreal'
USE_I18N = True
USE_TZ = True

# --- Static / Media ---
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'crm_app' / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'  # needed for collectstatic

# --- Auth redirects ---
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'login'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- Optional: basic hardening when DEBUG=False ---
if not DEBUG:
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    X_FRAME_OPTIONS = 'DENY'
