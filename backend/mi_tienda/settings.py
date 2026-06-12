"""
Archivo: settings.py
Descripcion: Configura las opciones principales del proyecto Django, incluyendo aplicaciones, middleware, base de datos, archivos estaticos, archivos media y seguridad basica.
Dependencias: os, pathlib, Django, WhiteNoise, Django REST Framework y aplicacion store
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    """
    Nombre: env_bool
    Descripcion: Convierte variables de entorno comunes en booleanos y rechaza valores invalidos.
    """
    raw_value = os.environ.get(name)

    if raw_value is None:
        return default

    value = raw_value.strip().lower()

    if value in ("1", "true", "yes", "on"):
        return True

    if value in ("0", "false", "no", "off"):
        return False

    raise ImproperlyConfigured(
        f"{name} debe ser booleano: true/false, yes/no, on/off o 1/0."
    )


def env_int(name, default, minimum=None):
    """
    Nombre: env_int
    Descripcion: Convierte una variable de entorno en entero y valida su minimo opcional.
    """
    raw_value = os.environ.get(name, default)

    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured(
            f"{name} debe ser un numero entero."
        ) from exc

    if minimum is not None and value < minimum:
        raise ImproperlyConfigured(
            f"{name} debe ser mayor o igual a {minimum}."
        )

    return value


def env_list(name, default=""):
    """
    Nombre: env_list
    Descripcion: Convierte una variable separada por comas en una lista limpia.
    """
    raw_value = os.environ.get(name, default)

    return [
        item.strip()
        for item in raw_value.split(",")
        if item.strip()
    ]


def env_choice(name, default, choices):
    """
    Nombre: env_choice
    Descripcion: Valida una variable de entorno contra opciones permitidas.
    """
    value = os.environ.get(name, default).strip().upper()

    if value not in choices:
        allowed_values = ", ".join(choices)
        raise ImproperlyConfigured(
            f"{name} debe ser uno de: {allowed_values}."
        )

    return value


def env_lower_choice(name, default, choices):
    """
    Nombre: env_lower_choice
    Descripcion: Valida una variable de entorno contra opciones permitidas en minuscula.
    """
    value = os.environ.get(name, default).strip().lower()

    if value not in choices:
        allowed_values = ", ".join(choices)
        raise ImproperlyConfigured(
            f"{name} debe ser uno de: {allowed_values}."
        )

    return value


def env_digits(name, default, min_digits=1, max_digits=None):
    """
    Nombre: env_digits
    Descripcion: Normaliza una variable de entorno dejando solo digitos y valida su longitud.
    """
    raw_value = os.environ.get(name, default)
    digits = "".join(
        char
        for char in str(raw_value)
        if char.isdigit()
    )

    if len(digits) < min_digits:
        raise ImproperlyConfigured(
            f"{name} debe contener al menos {min_digits} digito(s)."
        )

    if max_digits is not None and len(digits) > max_digits:
        raise ImproperlyConfigured(
            f"{name} debe contener maximo {max_digits} digito(s)."
        )

    return digits


def required_env(name):
    """
    Nombre: required_env
    Descripcion: Obtiene una variable obligatoria o detiene la configuracion.
    """
    value = os.environ.get(name, "").strip()

    if not value:
        raise ImproperlyConfigured(f"{name} debe estar configurada.")

    return value


def env_path(name, default):
    """
    Nombre: env_path
    Descripcion: Resuelve una ruta configurada por entorno desde la raiz del proyecto.
    """
    raw_value = os.environ.get(name)

    if not raw_value:
        return default

    path = Path(raw_value)

    if path.is_absolute():
        return path

    return PROJECT_ROOT / path


# =============================================================================
# CONFIGURACION GENERAL
# =============================================================================

DEBUG = env_bool("DJANGO_DEBUG", True)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")

if not SECRET_KEY and DEBUG:
    SECRET_KEY = 'django-insecure-+j0#xw2)7mu_=oc0k*xr50e3a%kq2)@a!z$-*p*#sg6*0$k%ze'

if not SECRET_KEY:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY debe estar configurada cuando DJANGO_DEBUG=False."
    )

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")

if not DEBUG and not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS debe estar configurado cuando DJANGO_DEBUG=False."
    )


# =============================================================================
# APLICACIONES INSTALADAS
# =============================================================================

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "store",
    "rest_framework",
]


# =============================================================================
# DJANGO REST FRAMEWORK
# =============================================================================

REST_FRAMEWORK = {
    "DEFAULT_THROTTLE_RATES": {
        "auth_anon": os.environ.get("AUTH_THROTTLE_RATE", "20/min"),
        "contact_anon": os.environ.get("CONTACT_THROTTLE_RATE", "10/hour"),
        "cart": os.environ.get("CART_THROTTLE_RATE", "60/min"),
        "checkout_user": os.environ.get("CHECKOUT_THROTTLE_RATE", "20/min"),
    },
}


# =============================================================================
# LIMITES DE REQUEST
# =============================================================================

DATA_UPLOAD_MAX_MEMORY_SIZE = env_int(
    "DJANGO_DATA_UPLOAD_MAX_MEMORY_SIZE",
    1024 * 1024,
    minimum=1,
)
FILE_UPLOAD_MAX_MEMORY_SIZE = env_int(
    "DJANGO_FILE_UPLOAD_MAX_MEMORY_SIZE",
    1024 * 1024,
    minimum=1,
)
DATA_UPLOAD_MAX_NUMBER_FIELDS = env_int(
    "DJANGO_DATA_UPLOAD_MAX_NUMBER_FIELDS",
    1000,
    minimum=1,
)
DATA_UPLOAD_MAX_NUMBER_FILES = env_int(
    "DJANGO_DATA_UPLOAD_MAX_NUMBER_FILES",
    20,
    minimum=1,
)


# =============================================================================
# MIDDLEWARE
# =============================================================================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "store.middleware.PermissionsPolicyMiddleware",
    "store.middleware.ApiCacheControlMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# =============================================================================
# RUTAS PRINCIPALES DEL PROYECTO
# =============================================================================

ROOT_URLCONF = "mi_tienda.urls"

WSGI_APPLICATION = "mi_tienda.wsgi.application"


# =============================================================================
# PLANTILLAS
# =============================================================================

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            BASE_DIR / "backend" / "templates",
        ],
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


# =============================================================================
# BASE DE DATOS
# =============================================================================

DB_ENGINE = os.environ.get("DJANGO_DB_ENGINE", "sqlite").lower().strip()

if DB_ENGINE == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": env_path("DJANGO_DB_NAME", BASE_DIR / "db.sqlite3"),
        }
    }
elif DB_ENGINE == "mysql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": required_env("DJANGO_DB_NAME"),
            "USER": required_env("DJANGO_DB_USER"),
            "PASSWORD": os.environ.get("DJANGO_DB_PASSWORD", ""),
            "HOST": os.environ.get("DJANGO_DB_HOST", "127.0.0.1"),
            "PORT": os.environ.get("DJANGO_DB_PORT", "3306"),
            "OPTIONS": {
                "charset": "utf8mb4",
            },
        }
    }
else:
    raise ImproperlyConfigured(
        "DJANGO_DB_ENGINE debe ser 'sqlite' o 'mysql'."
    )


# =============================================================================
# VALIDACION DE CONTRASEÑAS
# =============================================================================

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# =============================================================================
# INTERNACIONALIZACION
# =============================================================================

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# =============================================================================
# ARCHIVOS ESTATICOS
# =============================================================================

STATIC_URL = "/static/"

STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"


# =============================================================================
# ARCHIVOS MEDIA
# =============================================================================

MEDIA_URL = "/media/"

MEDIA_ROOT = BASE_DIR / "media"


# =============================================================================
# SEGURIDAD CSRF LOCAL
# =============================================================================

CSRF_TRUSTED_ORIGINS = env_list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    "http://127.0.0.1:8000,http://localhost:8000",
)


# =============================================================================
# SEGURIDAD PARA PRODUCCION
# =============================================================================

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = env_int(
    "DJANGO_SESSION_COOKIE_AGE",
    1209600,
    minimum=300,
)
CSRF_COOKIE_HTTPONLY = env_bool("DJANGO_CSRF_COOKIE_HTTPONLY", True)
CSRF_COOKIE_SAMESITE = "Lax"

SESSION_COOKIE_SECURE = env_bool(
    "DJANGO_SESSION_COOKIE_SECURE",
    not DEBUG,
)
CSRF_COOKIE_SECURE = env_bool(
    "DJANGO_CSRF_COOKIE_SECURE",
    not DEBUG,
)
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", False)
SECURE_HSTS_SECONDS = env_int(
    "DJANGO_SECURE_HSTS_SECONDS",
    0,
    minimum=0,
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool(
    "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS",
    False,
)
SECURE_HSTS_PRELOAD = env_bool("DJANGO_SECURE_HSTS_PRELOAD", False)
SECURE_CONTENT_TYPE_NOSNIFF = True
REFERRER_POLICY_CHOICES = (
    "no-referrer",
    "no-referrer-when-downgrade",
    "origin",
    "origin-when-cross-origin",
    "same-origin",
    "strict-origin",
    "strict-origin-when-cross-origin",
    "unsafe-url",
)
CROSS_ORIGIN_OPENER_POLICY_CHOICES = (
    "same-origin",
    "same-origin-allow-popups",
    "unsafe-none",
)
SECURE_REFERRER_POLICY = env_lower_choice(
    "DJANGO_SECURE_REFERRER_POLICY",
    "same-origin",
    REFERRER_POLICY_CHOICES,
)
SECURE_CROSS_ORIGIN_OPENER_POLICY = env_lower_choice(
    "DJANGO_SECURE_CROSS_ORIGIN_OPENER_POLICY",
    "same-origin",
    CROSS_ORIGIN_OPENER_POLICY_CHOICES,
)
PERMISSIONS_POLICY = os.environ.get(
    "DJANGO_PERMISSIONS_POLICY",
    "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
)
X_FRAME_OPTIONS = "DENY"

if env_bool("DJANGO_USE_X_FORWARDED_PROTO", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")


# =============================================================================
# CONFIGURACION DE CONTACTO Y CORREO
# =============================================================================

CONTACT_WHATSAPP_NUMBER = env_digits(
    "CONTACT_WHATSAPP_NUMBER",
    "573016604375",
    min_digits=7,
    max_digits=15,
)

DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL",
    "Vape Shop <no-reply@vape-shop.local>",
)

CONTACT_NOTIFICATION_EMAIL = os.environ.get(
    "CONTACT_NOTIFICATION_EMAIL",
    "admin@vape-shop.local",
)

EMAIL_BACKEND = os.environ.get(
    "DJANGO_EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)
EMAIL_TIMEOUT = env_int(
    "DJANGO_EMAIL_TIMEOUT",
    10,
    minimum=1,
)


# =============================================================================
# LOGGING Y TRAZABILIDAD
# =============================================================================

LOG_LEVEL_CHOICES = (
    "DEBUG",
    "INFO",
    "WARNING",
    "ERROR",
    "CRITICAL",
)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {
            "format": "[{levelname}] {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "loggers": {
        "store": {
            "handlers": ["console"],
            "level": env_choice(
                "DJANGO_STORE_LOG_LEVEL",
                "WARNING",
                LOG_LEVEL_CHOICES,
            ),
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": env_choice(
                "DJANGO_REQUEST_LOG_LEVEL",
                "ERROR",
                LOG_LEVEL_CHOICES,
            ),
            "propagate": False,
        },
    },
}


# =============================================================================
# CONFIGURACION DEFAULT DE MODELOS
# =============================================================================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
