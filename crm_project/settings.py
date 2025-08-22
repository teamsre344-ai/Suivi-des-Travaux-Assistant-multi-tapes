from pathlib import Path
from decouple import config
from django.core.management.utils import get_random_secret_key

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Core ---
SECRET_KEY = config("SECRET_KEY", default=get_random_secret_key())
DEBUG = config("DEBUG", cast=bool, default=True)


def _split(env_key: str, default_val: str = ""):
    return [
        x.strip() for x in config(env_key, default=default_val).split(",") if x.strip()
    ]


ALLOWED_HOSTS = _split("ALLOWED_HOSTS", "127.0.0.1,localhost")
CSRF_TRUSTED_ORIGINS = _split(
    "CSRF_TRUSTED_ORIGINS", "http://127.0.0.1,http://localhost"
)

# --- Apps ---
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "crm_app",
    "crispy_forms",
    "crispy_bootstrap5",
    "django.contrib.postgres",
    "axes",
    "debug_toolbar",
]

CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "debug_toolbar.middleware.DebugToolbarMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "crm_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "crm_app" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "crm_project.wsgi.application"
ASGI_APPLICATION = "crm_project.asgi.application"

# --- Database (Postgres via .env, else SQLite fallback) ---
ENGINE = config("DB_ENGINE", default="postgresql").lower()
if ENGINE == "postgresql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": config("DB_NAME", default="crm_msui"),
            "USER": config("DB_USER", default="postgres"),
            "PASSWORD": config("DB_PASSWORD", default="postgres"),
            "HOST": config("DB_HOST", default="localhost"),
            "PORT": config("DB_PORT", default="5432"),
            "CONN_MAX_AGE": config("DB_CONN_MAX_AGE", cast=int, default=60),
            "OPTIONS": {
                # Example: set schema -> 'options': '-c search_path=public'
            },
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(BASE_DIR / config("DB_NAME", default="db.sqlite3")),
        }
    }

# --- Passwordless login flags ---
PASSWORDLESS_LOGIN = True  # enable email-only login
PASSWORDLESS_ALLOWED_DOMAINS = ["lgisolutions.com"]
PASSWORDLESS_FALLBACK_DOMAINS = [
    "logibec.com",
    "logibe.com",
]  # old domains that we will match by local-part
PASSWORDLESS_AUTO_UPDATE_EMAIL = (
    True  # auto-rewrite to the @lgisolutions.com email on first login
)


MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "/media/"

# --- I18N / TZ ---
LANGUAGE_CODE = "fr-ca"
TIME_ZONE = "America/Montreal"
USE_I18N = True
USE_TZ = True

# --- Static / Media ---
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "crm_app" / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- Auth redirects ---
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesBackend",
    "crm_app.backends.EmailBackend",
    "django.contrib.auth.backends.ModelBackend",
]

AXES_FAILURE_LIMIT = 5

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# -------------------------------
# Team directory & email login
# -------------------------------
# Allow passwordless sign-in if the email is whitelisted below.
TEAM_EMAIL_LOGIN_ENABLED = True

# Map company emails to canonical profile (names + full role title shown in UI).
# ➜ Fill this with real emails/titles from your org chart.
TEAM_DIRECTORY = {
    "mahmoud.feki@lgisolutions.com": {
        "first_name": "Mahmoud",
        "last_name": "Feki",
        "role": "Spécialiste principal, déploiement",
        "is_manager": False,
    },
    "ruben.geghamyan@lgisolutions.com": {
        "first_name": "Ruben",
        "last_name": "Geghamyan",
        "role": "Spécialiste principal, déploiement",
        "is_manager": False,
    },
    "eric.lamontagne@lgisolutions.com": {
        "first_name": "Eric",
        "last_name": "Lamontagne",
        "role": "Spécialiste principal, déploiement",
        "is_manager": False,
    },
    "frederic.rousseau@lgisolutions.com": {
        "first_name": "Frédéric",
        "last_name": "Rousseau",
        "role": "Spécialiste principal, déploiement",
        "is_manager": False,
    },
    "eric.champagne@lgisolutions.com": {
        "first_name": "Éric",
        "last_name": "Champagne",
        "role": "Spécialiste principal, déploiement",
        "is_manager": False,
    },
    "marc.banville@lgisolutions.com": {
        "first_name": "Marc",
        "last_name": "Banville",
        "role": "Spécialiste principal, déploiement",
        "is_manager": False,
    },
    "halimatou.ly@lgisolutions.com": {
        "first_name": "Halimatou",
        "last_name": "Ly",
        "role": "Spécialiste principal, déploiement",
        "is_manager": False,
    },
    "romeo.kutnjem@lgisolutions.com": {
        "first_name": "Roméo",
        "last_name": "Kutnjem",
        "role": "Spécialiste, déploiement des solutions",
        "is_manager": False,
    },
    "sylvain.berthiaume@lgisolutions.com": {
        "first_name": "Sylvain",
        "last_name": "Berthiaume",
        "role": "Spécialiste principal, déploiement",
        "is_manager": False,
    },
    "masamba.lema@lgisolutions.com": {
        "first_name": "Masamba",
        "last_name": "Lema",
        "role": "Spécialiste principal, déploiement",
        "is_manager": False,
    },
    "taoufik.toughrai@lgisolutions.com": {
        "first_name": "Taoufik",
        "last_name": "Toughrai",
        "role": "Spécialiste, déploiement des solutions",
        "is_manager": False,
    },
    "frank.binde@lgisolutions.com": {
        "first_name": "Mambibe Frank",
        "last_name": "Merari",
        "role": "Spécialiste, déploiement des solutions",
        "is_manager": False,
    },
    "dounia.elbaine@lgisolutions.com": {
        "first_name": "Dounia",
        "last_name": "ElBaine",
        "role": "Conseiller en planification",
        "is_manager": True,
    },
    "ann-pier.lucas-mercier@lgisolutions.com": {
        "first_name": "Ann-Pier",
        "last_name": "Lucas-Mercier",
        "role": "Conseiller en planification",
        "is_manager": False,
    },
    "jessyca.lantagne@lgisolutions.com": {
        "first_name": "Jessyca",
        "last_name": "Lantagne",
        "role": "Conseiller en planification",
        "is_manager": True,
    },
    "pierre.veillard@lgisolutions.com": {
        "first_name": "Pierre Ernest",
        "last_name": "Veillard",
        "role": "Spécialiste principal, déploiement",
        "is_manager": False,
    },
    # NEW – Patrick (manager)
    "patrick.savard@lgisolutions.com": {
        "first_name": "Patrick",
        "last_name": "Savard",
        "role": "Gestionnaire d’équipe, déploiement (600-IFS – Services gérés)",
        "is_manager": True,
    },
}

# --- Optional: basic hardening when DEBUG=False ---
# --- Debug Toolbar ---
INTERNAL_IPS = ["127.0.0.1"]

# --- Logging ---
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}

# --- Optional: basic hardening when DEBUG=False ---
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    X_FRAME_OPTIONS = "DENY"
