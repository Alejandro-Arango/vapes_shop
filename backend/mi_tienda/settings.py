"""
Archivo: settings.py
Descripcion: Configura las opciones principales del proyecto Django, incluyendo aplicaciones, middleware, base de datos, archivos estaticos, archivos media y seguridad basica.
Dependencias: os, pathlib, Django, WhiteNoise, Django REST Framework y aplicacion store
"""

import os
import re
from ipaddress import ip_address
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


def env_port(name, default):
    """
    Nombre: env_port
    Descripcion: Valida un puerto TCP y lo retorna como texto para Django.
    """
    value = env_int(name, default, minimum=1)

    if value > 65535:
        raise ImproperlyConfigured(
            f"{name} debe estar entre 1 y 65535."
        )

    return str(value)


def env_port_int(name, default):
    """
    Nombre: env_port_int
    Descripcion: Valida un puerto TCP y lo retorna como entero.
    """
    return int(env_port(name, default))


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


def env_throttle_rate(name, default):
    """
    Nombre: env_throttle_rate
    Descripcion: Valida tasas de uso para Django REST Framework.
    """
    value = os.environ.get(name, default).strip().lower()
    valid_periods = (
        "s",
        "sec",
        "second",
        "seconds",
        "m",
        "min",
        "minute",
        "minutes",
        "h",
        "hour",
        "hours",
        "d",
        "day",
        "days",
    )

    parts = value.split("/")

    if len(parts) != 2:
        raise ImproperlyConfigured(
            f"{name} debe tener formato cantidad/periodo, por ejemplo 20/min."
        )

    quantity, period = parts

    if not quantity.isdigit() or int(quantity) <= 0:
        raise ImproperlyConfigured(
            f"{name} debe iniciar con una cantidad positiva."
        )

    if period not in valid_periods:
        raise ImproperlyConfigured(
            f"{name} debe usar un periodo valido: s, m, h, d, second, minute, hour o day."
        )

    return value


def env_ip_list(name, default=""):
    """
    Nombre: env_ip_list
    Descripcion: Convierte una lista de IPs separadas por comas y rechaza valores invalidos.
    """
    ip_values = []

    for value in env_list(name, default):
        try:
            ip_values.append(str(ip_address(value)))
        except ValueError as exc:
            raise ImproperlyConfigured(
                f"{name} contiene una IP invalida: {value}."
            ) from exc

    return ip_values


def env_admin_url_path(name, default):
    """
    Nombre: env_admin_url_path
    Descripcion: Normaliza la ruta del panel administrativo.
    """
    value = os.environ.get(name, default).strip().strip("/")

    if not value:
        raise ImproperlyConfigured(f"{name} no puede estar vacia.")

    if not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_-]*(/[A-Za-z0-9][A-Za-z0-9_-]*)*",
        value,
    ):
        raise ImproperlyConfigured(
            f"{name} debe ser una ruta relativa con segmentos seguros."
        )

    return f"{value}/"


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
    "mi_tienda.apps.StoreAdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "store",
    "rest_framework",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "django_otp.plugins.otp_static",
]


# =============================================================================
# DJANGO REST FRAMEWORK
# =============================================================================

REST_FRAMEWORK = {
    "DEFAULT_THROTTLE_RATES": {
        "auth_anon": env_throttle_rate("AUTH_THROTTLE_RATE", "20/min"),
        "auth_user": env_throttle_rate("AUTH_USER_THROTTLE_RATE", "10/min"),
        "contact_anon": env_throttle_rate("CONTACT_THROTTLE_RATE", "10/hour"),
        "cart": env_throttle_rate("CART_THROTTLE_RATE", "60/min"),
        "checkout_user": env_throttle_rate("CHECKOUT_THROTTLE_RATE", "20/min"),
    },
}


# =============================================================================
# CACHE
# =============================================================================

CACHE_BACKEND_CHOICES = ("locmem", "database")
CACHE_BACKEND = env_lower_choice(
    "DJANGO_CACHE_BACKEND",
    "locmem",
    CACHE_BACKEND_CHOICES,
)

if CACHE_BACKEND == "database":
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.db.DatabaseCache",
            "LOCATION": os.environ.get("DJANGO_CACHE_TABLE", "django_cache"),
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "vapes-shop-local-cache",
        }
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
    "store.middleware.RequestObservabilityMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "store.middleware.AdminAccessMiddleware",
    "store.middleware.PermissionsPolicyMiddleware",
    "store.middleware.ContentSecurityPolicyMiddleware",
    "store.middleware.ApiCacheControlMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "store.middleware.AdminSessionSecurityMiddleware",
    "store.middleware.AdminLoginThrottleMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# =============================================================================
# RUTAS PRINCIPALES DEL PROYECTO
# =============================================================================

ROOT_URLCONF = "mi_tienda.urls"

WSGI_APPLICATION = "mi_tienda.wsgi.application"

ADMIN_URL_PATH = env_admin_url_path("DJANGO_ADMIN_URL_PATH", "admin")
ADMIN_ALLOWED_IPS = tuple(env_ip_list("DJANGO_ADMIN_ALLOWED_IPS", ""))
ADMIN_SESSION_COOKIE_AGE = env_int(
    "DJANGO_ADMIN_SESSION_COOKIE_AGE",
    1800,
    minimum=300,
)
ADMIN_LOGIN_MAX_ATTEMPTS = env_int(
    "DJANGO_ADMIN_LOGIN_MAX_ATTEMPTS",
    5,
    minimum=1,
)
ADMIN_LOGIN_LOCKOUT_SECONDS = env_int(
    "DJANGO_ADMIN_LOGIN_LOCKOUT_SECONDS",
    900,
    minimum=60,
)

OTP_TOTP_ISSUER = os.environ.get(
    "DJANGO_OTP_TOTP_ISSUER",
    "Vape Shop Admin",
).strip()
OTP_TOTP_THROTTLE_FACTOR = env_int(
    "DJANGO_OTP_TOTP_THROTTLE_FACTOR",
    1,
    minimum=1,
)
OTP_STATIC_THROTTLE_FACTOR = env_int(
    "DJANGO_OTP_STATIC_THROTTLE_FACTOR",
    1,
    minimum=1,
)
OTP_ADMIN_HIDE_SENSITIVE_DATA = True


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

DB_ENGINE_CHOICES = ("sqlite", "mysql")
DB_ENGINE = env_lower_choice(
    "DJANGO_DB_ENGINE",
    "sqlite",
    DB_ENGINE_CHOICES,
)

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
            "PORT": env_port("DJANGO_DB_PORT", "3306"),
            "CONN_MAX_AGE": env_int(
                "DJANGO_DB_CONN_MAX_AGE",
                60,
                minimum=0,
            ),
            "CONN_HEALTH_CHECKS": True,
            "OPTIONS": {
                "charset": "utf8mb4",
                "connect_timeout": env_int(
                    "DJANGO_DB_CONNECT_TIMEOUT",
                    10,
                    minimum=1,
                ),
                "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            },
        }
    }


# =============================================================================
# VALIDACION DE CONTRASEÑAS
# =============================================================================

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {
            "min_length": env_int(
                "DJANGO_PASSWORD_MIN_LENGTH",
                12,
                minimum=8,
            ),
        },
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

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}


# =============================================================================
# ARCHIVOS MEDIA
# =============================================================================

MEDIA_URL = "/media/"

MEDIA_ROOT = env_path("DJANGO_MEDIA_ROOT", BASE_DIR / "media")


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
CONTENT_SECURITY_POLICY = os.environ.get(
    "DJANGO_CONTENT_SECURITY_POLICY",
    (
        "default-src 'self'; "
        "base-uri 'self'; "
        "object-src 'none'; "
        "frame-ancestors 'none'; "
        "form-action 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "media-src 'self'; "
        "worker-src 'self'"
    ),
)
X_FRAME_OPTIONS = "DENY"

if env_bool("DJANGO_USE_X_FORWARDED_PROTO", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

TRUST_X_FORWARDED_FOR = env_bool("DJANGO_TRUST_X_FORWARDED_FOR", False)


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

ORDER_NOTIFICATION_EMAIL = os.environ.get(
    "ORDER_NOTIFICATION_EMAIL",
    CONTACT_NOTIFICATION_EMAIL,
)
INVENTORY_NOTIFICATION_EMAIL = os.environ.get(
    "INVENTORY_NOTIFICATION_EMAIL",
    ORDER_NOTIFICATION_EMAIL,
)

EMAIL_BACKEND = os.environ.get(
    "DJANGO_EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = os.environ.get("DJANGO_EMAIL_HOST", "")
EMAIL_PORT = env_port_int("DJANGO_EMAIL_PORT", 587)
EMAIL_HOST_USER = os.environ.get("DJANGO_EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("DJANGO_EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("DJANGO_EMAIL_USE_TLS", True)
EMAIL_USE_SSL = env_bool("DJANGO_EMAIL_USE_SSL", False)
EMAIL_TIMEOUT = env_int(
    "DJANGO_EMAIL_TIMEOUT",
    10,
    minimum=1,
)
PASSWORD_RESET_TIMEOUT = env_int(
    "DJANGO_PASSWORD_RESET_TIMEOUT",
    3600,
    minimum=300,
)

if EMAIL_USE_TLS and EMAIL_USE_SSL:
    raise ImproperlyConfigured(
        "DJANGO_EMAIL_USE_TLS y DJANGO_EMAIL_USE_SSL no pueden estar activos al mismo tiempo."
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
LOG_FORMAT_CHOICES = (
    "simple",
    "json",
)
LOG_FORMAT = env_lower_choice(
    "DJANGO_LOG_FORMAT",
    "simple",
    LOG_FORMAT_CHOICES,
)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {
            "format": "[{levelname}] {name} request_id={request_id}: {message}",
            "style": "{",
        },
        "json": {
            "()": "store.logging_utils.JsonFormatter",
        },
    },
    "filters": {
        "request_context": {
            "()": "store.logging_utils.RequestContextFilter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": LOG_FORMAT,
            "filters": ["request_context"],
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
        "store.request": {
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
