"""
Archivo: production_check.py
Descripcion: Comando para validar configuracion minima antes de desplegar en produccion.
Dependencias: Django settings y BaseCommand
"""

from email.utils import parseaddr
from ipaddress import ip_address, ip_network
from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email


PLACEHOLDER_SECRET_PARTS = (
    "django-insecure",
    "cambia",
    "change-me",
    "reemplaza",
    "placeholder",
    "secret-key",
)
LOCAL_ORIGINS = (
    "http://127.0.0.1",
    "http://localhost",
)
LOCAL_HOSTS = (
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "[::1]",
)
RESERVED_HOSTS = (
    "example.com",
    "example.net",
    "example.org",
)
RESERVED_HOST_SUFFIXES = (
    ".example",
    ".invalid",
    ".localhost",
    ".test",
)
DOCUMENTATION_IP_NETWORKS = tuple(
    ip_network(network)
    for network in (
        "192.0.2.0/24",
        "198.51.100.0/24",
        "203.0.113.0/24",
    )
)
UNSAFE_EMAIL_BACKENDS = (
    "django.core.mail.backends.console.EmailBackend",
    "django.core.mail.backends.locmem.EmailBackend",
    "django.core.mail.backends.dummy.EmailBackend",
)
UNSAFE_CACHE_BACKENDS = (
    "django.core.cache.backends.locmem.LocMemCache",
    "django.core.cache.backends.dummy.DummyCache",
)
MAX_SESSION_COOKIE_AGE = 604800
MAX_PASSWORD_RESET_TIMEOUT = 3600


class Command(BaseCommand):
    """
    Nombre: Command
    Descripcion: Revisa riesgos comunes de despliegue que Django no bloquea por defecto.
    """

    help = "Valida configuracion minima para produccion real."

    def add_arguments(self, parser):
        parser.add_argument(
            "--allow-sqlite",
            action="store_true",
            help="Permite SQLite para despliegues controlados o demos internas.",
        )

    def handle(self, *args, **options):
        errors = []
        warnings = []

        self.check_debug(errors)
        self.check_secret_key(errors)
        self.check_hosts(errors)
        self.check_csrf(errors)
        self.check_https(errors)
        self.check_proxy_headers(errors)
        self.check_content_security_policy(errors)
        self.check_browser_security_headers(errors)
        self.check_database(errors, options["allow_sqlite"])
        self.check_cache(errors)
        self.check_observability(errors)
        self.check_admin(errors, warnings)
        self.check_email(errors, warnings)
        self.check_contact(errors)

        for warning in warnings:
            self.stdout.write(self.style.WARNING(f"WARNING: {warning}"))

        if errors:
            for error in errors:
                self.stderr.write(self.style.ERROR(f"ERROR: {error}"))

            raise CommandError(
                "La configuracion no cumple los minimos de produccion."
            )

        self.stdout.write(
            self.style.SUCCESS("Configuracion de produccion validada.")
        )

    def check_debug(self, errors):
        if settings.DEBUG:
            errors.append("DJANGO_DEBUG debe ser False.")

    def check_secret_key(self, errors):
        secret_key = getattr(settings, "SECRET_KEY", "")
        normalized_secret = secret_key.lower()

        if len(secret_key) < 50:
            errors.append("DJANGO_SECRET_KEY debe tener al menos 50 caracteres.")

        if any(part in normalized_secret for part in PLACEHOLDER_SECRET_PARTS):
            errors.append("DJANGO_SECRET_KEY no debe usar valores de ejemplo.")

    def check_hosts(self, errors):
        allowed_hosts = getattr(settings, "ALLOWED_HOSTS", [])

        if not allowed_hosts:
            errors.append("DJANGO_ALLOWED_HOSTS debe incluir dominios reales.")

        if "*" in allowed_hosts:
            errors.append("DJANGO_ALLOWED_HOSTS no debe usar '*'.")

        if any(
            "://" in str(host) or "/" in str(host)
            for host in allowed_hosts
        ):
            errors.append(
                "DJANGO_ALLOWED_HOSTS debe contener hostnames, no URLs completas."
            )

        if any(self.is_local_allowed_host(host) for host in allowed_hosts):
            errors.append(
                "DJANGO_ALLOWED_HOSTS no debe usar hosts locales en produccion."
            )

        if any(self.is_reserved_allowed_host(host) for host in allowed_hosts):
            errors.append(
                "DJANGO_ALLOWED_HOSTS no debe usar dominios reservados o de ejemplo."
            )

    def is_local_allowed_host(self, host):
        normalized_host = str(host).strip().lower()

        if normalized_host.startswith("[::1]"):
            return True

        if normalized_host.count(":") == 1:
            normalized_host = normalized_host.rsplit(":", 1)[0]

        return normalized_host in LOCAL_HOSTS

    def is_reserved_allowed_host(self, host):
        normalized_host = str(host).strip().lower().lstrip(".").rstrip(".")

        return (
            any(
                normalized_host == reserved_host
                or normalized_host.endswith(f".{reserved_host}")
                for reserved_host in RESERVED_HOSTS
            )
            or normalized_host.endswith(RESERVED_HOST_SUFFIXES)
        )

    def check_csrf(self, errors):
        trusted_origins = getattr(settings, "CSRF_TRUSTED_ORIGINS", [])
        allowed_hosts = getattr(settings, "ALLOWED_HOSTS", [])

        if not trusted_origins:
            errors.append("DJANGO_CSRF_TRUSTED_ORIGINS debe estar configurado.")

        for origin in trusted_origins:
            if origin.startswith(LOCAL_ORIGINS):
                errors.append(
                    "DJANGO_CSRF_TRUSTED_ORIGINS no debe usar localhost en produccion."
                )

            if not origin.startswith("https://"):
                errors.append(
                    "DJANGO_CSRF_TRUSTED_ORIGINS debe usar origenes https."
                )

            if not self.csrf_origin_matches_allowed_hosts(origin, allowed_hosts):
                errors.append(
                    (
                        "DJANGO_CSRF_TRUSTED_ORIGINS debe corresponder a "
                        "DJANGO_ALLOWED_HOSTS."
                    )
                )

    def csrf_origin_matches_allowed_hosts(self, origin, allowed_hosts):
        parsed_origin = urlparse(origin)
        origin_host = (parsed_origin.hostname or "").lower()

        if not origin_host:
            return False

        for host in allowed_hosts:
            normalized_host = str(host).strip().lower()

            if normalized_host.startswith("."):
                base_domain = normalized_host[1:]

                if (
                    origin_host == base_domain
                    or origin_host.endswith(f".{base_domain}")
                ):
                    return True

            if origin_host == normalized_host:
                return True

        return False

    def check_https(self, errors):
        safe_samesite_values = ("Lax", "Strict")

        if settings.SESSION_COOKIE_AGE > MAX_SESSION_COOKIE_AGE:
            errors.append(
                "DJANGO_SESSION_COOKIE_AGE no debe superar 604800 segundos."
            )

        if settings.PASSWORD_RESET_TIMEOUT > MAX_PASSWORD_RESET_TIMEOUT:
            errors.append(
                "DJANGO_PASSWORD_RESET_TIMEOUT no debe superar 3600 segundos."
            )

        if not settings.SESSION_COOKIE_HTTPONLY:
            errors.append("SESSION_COOKIE_HTTPONLY debe estar activo.")

        if settings.SESSION_COOKIE_SAMESITE not in safe_samesite_values:
            errors.append("SESSION_COOKIE_SAMESITE debe ser Lax o Strict.")

        if not settings.CSRF_COOKIE_HTTPONLY:
            errors.append("DJANGO_CSRF_COOKIE_HTTPONLY debe ser True.")

        if settings.CSRF_COOKIE_SAMESITE not in safe_samesite_values:
            errors.append("CSRF_COOKIE_SAMESITE debe ser Lax o Strict.")

        if not settings.SESSION_COOKIE_SECURE:
            errors.append("DJANGO_SESSION_COOKIE_SECURE debe ser True.")

        if not settings.CSRF_COOKIE_SECURE:
            errors.append("DJANGO_CSRF_COOKIE_SECURE debe ser True.")

        if not settings.SECURE_SSL_REDIRECT:
            errors.append("DJANGO_SECURE_SSL_REDIRECT debe ser True.")

        if settings.SECURE_HSTS_SECONDS < 31536000:
            errors.append("DJANGO_SECURE_HSTS_SECONDS debe ser al menos 31536000.")

        if not settings.SECURE_HSTS_INCLUDE_SUBDOMAINS:
            errors.append("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS debe ser True.")

        if not settings.SECURE_HSTS_PRELOAD:
            errors.append("DJANGO_SECURE_HSTS_PRELOAD debe ser True.")

    def check_proxy_headers(self, errors):
        expected_proxy_header = ("HTTP_X_FORWARDED_PROTO", "https")

        if getattr(settings, "SECURE_PROXY_SSL_HEADER", None) != (
            expected_proxy_header
        ):
            errors.append(
                "DJANGO_USE_X_FORWARDED_PROTO debe estar activo tras el proxy."
            )

        if not getattr(settings, "TRUST_X_FORWARDED_FOR", False):
            errors.append(
                "DJANGO_TRUST_X_FORWARDED_FOR debe estar activo tras el proxy confiable."
            )

    def check_content_security_policy(self, errors):
        policy = getattr(settings, "CONTENT_SECURITY_POLICY", "")
        required_directives = (
            "default-src 'self'",
            "base-uri 'self'",
            "object-src 'none'",
            "frame-ancestors 'none'",
            "script-src 'self'",
        )

        if not policy:
            errors.append("DJANGO_CONTENT_SECURITY_POLICY debe estar configurada.")
            return

        for directive in required_directives:
            if directive not in policy:
                errors.append(
                    f"DJANGO_CONTENT_SECURITY_POLICY debe incluir {directive}."
                )

        if "'unsafe-eval'" in policy:
            errors.append(
                "DJANGO_CONTENT_SECURITY_POLICY no debe permitir 'unsafe-eval'."
            )

    def check_browser_security_headers(self, errors):
        if not getattr(settings, "SECURE_CONTENT_TYPE_NOSNIFF", False):
            errors.append("SECURE_CONTENT_TYPE_NOSNIFF debe estar activo.")

        if getattr(settings, "X_FRAME_OPTIONS", "") != "DENY":
            errors.append("X_FRAME_OPTIONS debe ser DENY.")

        referrer_policy = getattr(settings, "SECURE_REFERRER_POLICY", "")

        if referrer_policy in ("unsafe-url", "no-referrer-when-downgrade"):
            errors.append(
                "DJANGO_SECURE_REFERRER_POLICY no debe ser permisiva."
            )

        if getattr(settings, "SECURE_CROSS_ORIGIN_OPENER_POLICY", "") != (
            "same-origin"
        ):
            errors.append(
                "DJANGO_SECURE_CROSS_ORIGIN_OPENER_POLICY debe ser same-origin."
            )

        permissions_policy = getattr(settings, "PERMISSIONS_POLICY", "")
        required_permissions = (
            "camera=()",
            "microphone=()",
            "geolocation=()",
            "payment=()",
        )

        for directive in required_permissions:
            if directive not in permissions_policy:
                errors.append(
                    f"DJANGO_PERMISSIONS_POLICY debe incluir {directive}."
                )

        required_middleware = {
            "store.middleware.ContentSecurityPolicyMiddleware",
            "store.middleware.PermissionsPolicyMiddleware",
        }

        if not required_middleware.issubset(set(settings.MIDDLEWARE)):
            errors.append(
                "La aplicacion debe activar middleware de CSP y Permissions-Policy."
            )

    def check_database(self, errors, allow_sqlite):
        database = settings.DATABASES["default"]
        engine = database["ENGINE"]

        if "sqlite3" in engine and not allow_sqlite:
            errors.append(
                "SQLite no es recomendado para produccion real; usa MySQL/PostgreSQL."
            )

        password = str(database.get("PASSWORD", ""))

        if "sqlite3" not in engine and (
            not password or any(part in password.lower() for part in ("cambia", "password"))
        ):
            errors.append("La base de datos productiva debe tener una contrasena real.")

        if "mysql" in engine:
            if database.get("CONN_MAX_AGE", 0) <= 0:
                errors.append(
                    "DJANGO_DB_CONN_MAX_AGE debe reutilizar conexiones MySQL."
                )

            if not database.get("CONN_HEALTH_CHECKS"):
                errors.append(
                    "La base de datos MySQL debe activar CONN_HEALTH_CHECKS."
                )

            options = database.get("OPTIONS", {})

            if options.get("connect_timeout", 0) < 1:
                errors.append(
                    "DJANGO_DB_CONNECT_TIMEOUT debe limitar la conexion MySQL."
                )

            if "STRICT_TRANS_TABLES" not in options.get("init_command", ""):
                errors.append(
                    "MySQL debe usar STRICT_TRANS_TABLES para evitar truncamientos."
                )

    def check_cache(self, errors):
        cache_backend = settings.CACHES["default"]["BACKEND"]

        if cache_backend in UNSAFE_CACHE_BACKENDS:
            errors.append(
                "El cache por defecto no debe ser LocMem/Dummy en produccion."
            )

    def check_observability(self, errors):
        if getattr(settings, "LOG_FORMAT", "simple") != "json":
            errors.append("DJANGO_LOG_FORMAT debe ser json en produccion.")

        required_middleware = {
            "store.middleware.RequestObservabilityMiddleware",
        }

        if not required_middleware.issubset(set(settings.MIDDLEWARE)):
            errors.append(
                "La aplicacion debe activar middleware de correlacion de solicitudes."
            )

    def check_admin(self, errors, warnings):
        if settings.ADMIN_URL_PATH == "admin/":
            errors.append("DJANGO_ADMIN_URL_PATH debe cambiar la ruta /admin/.")

        if not settings.ADMIN_ALLOWED_IPS:
            errors.append("DJANGO_ADMIN_ALLOWED_IPS debe restringir el admin por IP.")

        for allowed_ip in settings.ADMIN_ALLOWED_IPS:
            if self.is_unsafe_admin_allowed_ip(allowed_ip):
                errors.append(
                    (
                        "DJANGO_ADMIN_ALLOWED_IPS no debe usar IPs locales, "
                        "reservadas o de documentacion."
                    )
                )
                break

        if settings.ADMIN_SESSION_COOKIE_AGE > 3600:
            errors.append(
                "DJANGO_ADMIN_SESSION_COOKIE_AGE no debe superar 3600 segundos."
            )

        if settings.ADMIN_LOGIN_MAX_ATTEMPTS > 10:
            errors.append(
                "DJANGO_ADMIN_LOGIN_MAX_ATTEMPTS no debe superar 10."
            )

        if settings.ADMIN_LOGIN_LOCKOUT_SECONDS < 300:
            errors.append(
                "DJANGO_ADMIN_LOGIN_LOCKOUT_SECONDS debe ser al menos 300."
            )

        if not getattr(settings, "OTP_ADMIN_HIDE_SENSITIVE_DATA", False):
            errors.append("OTP_ADMIN_HIDE_SENSITIVE_DATA debe estar activo.")

        required_apps = {
            "django_otp",
            "django_otp.plugins.otp_totp",
            "django_otp.plugins.otp_static",
        }

        if not required_apps.issubset(set(settings.INSTALLED_APPS)):
            errors.append(
                "El admin debe tener django-otp, TOTP y codigos estaticos instalados."
            )

        required_middleware = {
            "django_otp.middleware.OTPMiddleware",
            "store.middleware.AdminSessionSecurityMiddleware",
            "store.middleware.AdminLoginThrottleMiddleware",
        }

        if not required_middleware.issubset(set(settings.MIDDLEWARE)):
            errors.append(
                "El admin debe tener middleware OTP, sesion corta y bloqueo de intentos."
            )

    def is_unsafe_admin_allowed_ip(self, value):
        try:
            parsed_ip = ip_address(str(value).strip())
        except ValueError:
            return True

        return (
            parsed_ip.is_loopback
            or parsed_ip.is_unspecified
            or parsed_ip.is_multicast
            or parsed_ip.is_link_local
            or any(
                parsed_ip in documentation_network
                for documentation_network in DOCUMENTATION_IP_NETWORKS
            )
        )

    def check_email(self, errors, warnings):
        email_backend = getattr(settings, "EMAIL_BACKEND", "")

        if email_backend in UNSAFE_EMAIL_BACKENDS:
            errors.append("DJANGO_EMAIL_BACKEND debe ser un backend real de correo.")

        if email_backend == "django.core.mail.backends.smtp.EmailBackend":
            email_host = getattr(settings, "EMAIL_HOST", "")

            if not email_host:
                errors.append("DJANGO_EMAIL_HOST debe estar configurado para SMTP.")
            elif self.is_malformed_service_host(email_host):
                errors.append(
                    (
                        "DJANGO_EMAIL_HOST debe contener un hostname sin "
                        "esquema, ruta ni puerto."
                    )
                )
            elif self.is_local_allowed_host(email_host):
                errors.append(
                    "DJANGO_EMAIL_HOST no debe usar hosts locales en produccion."
                )
            elif self.is_reserved_allowed_host(email_host):
                errors.append(
                    "DJANGO_EMAIL_HOST no debe usar dominios reservados o de ejemplo."
                )

            email_user = getattr(settings, "EMAIL_HOST_USER", "")
            email_password = getattr(settings, "EMAIL_HOST_PASSWORD", "")

            if not email_user:
                errors.append(
                    "DJANGO_EMAIL_HOST_USER debe estar configurado para SMTP."
                )
            elif self.has_placeholder_value(email_user):
                errors.append(
                    "DJANGO_EMAIL_HOST_USER no debe usar valores de ejemplo."
                )

            if not email_password:
                errors.append(
                    "DJANGO_EMAIL_HOST_PASSWORD debe estar configurado para SMTP."
                )
            elif self.has_placeholder_value(email_password):
                errors.append(
                    "DJANGO_EMAIL_HOST_PASSWORD no debe usar valores de ejemplo."
                )

            if settings.EMAIL_USE_TLS and settings.EMAIL_USE_SSL:
                errors.append(
                    "DJANGO_EMAIL_USE_TLS y DJANGO_EMAIL_USE_SSL no pueden estar activos al mismo tiempo."
                )
            elif not settings.EMAIL_USE_TLS and not settings.EMAIL_USE_SSL:
                errors.append(
                    "DJANGO_EMAIL_USE_TLS o DJANGO_EMAIL_USE_SSL debe estar activo para SMTP."
                )

        default_from = getattr(settings, "DEFAULT_FROM_EMAIL", "")
        notification_email = getattr(settings, "CONTACT_NOTIFICATION_EMAIL", "")
        order_notification_email = getattr(settings, "ORDER_NOTIFICATION_EMAIL", "")
        inventory_notification_email = getattr(settings, "INVENTORY_NOTIFICATION_EMAIL", "")

        if "vape-shop.local" in default_from:
            errors.append("DEFAULT_FROM_EMAIL no debe usar vape-shop.local.")

        if "vape-shop.local" in notification_email:
            errors.append("CONTACT_NOTIFICATION_EMAIL no debe usar vape-shop.local.")

        if "vape-shop.local" in order_notification_email:
            errors.append("ORDER_NOTIFICATION_EMAIL no debe usar vape-shop.local.")

        if "vape-shop.local" in inventory_notification_email:
            errors.append("INVENTORY_NOTIFICATION_EMAIL no debe usar vape-shop.local.")

        if not default_from:
            errors.append("DEFAULT_FROM_EMAIL debe estar configurado.")

        if not notification_email:
            errors.append("CONTACT_NOTIFICATION_EMAIL debe estar configurado.")

        if not order_notification_email:
            errors.append("ORDER_NOTIFICATION_EMAIL debe estar configurado.")

        if not inventory_notification_email:
            errors.append("INVENTORY_NOTIFICATION_EMAIL debe estar configurado.")

        for value, label in (
            (default_from, "DEFAULT_FROM_EMAIL"),
            (notification_email, "CONTACT_NOTIFICATION_EMAIL"),
            (order_notification_email, "ORDER_NOTIFICATION_EMAIL"),
            (inventory_notification_email, "INVENTORY_NOTIFICATION_EMAIL"),
        ):
            if not value:
                continue

            if not self.has_valid_email_address(value):
                errors.append(f"{label} debe contener un correo valido.")
                continue

            if self.has_reserved_email_domain(value):
                errors.append(
                    f"{label} no debe usar dominios reservados o de ejemplo."
                )

    def has_placeholder_value(self, value):
        normalized_value = str(value).strip().lower()

        return any(
            part in normalized_value
            for part in PLACEHOLDER_SECRET_PARTS
        )

    def is_malformed_service_host(self, value):
        normalized_value = str(value).strip()

        return (
            not normalized_value
            or "://" in normalized_value
            or "/" in normalized_value
            or ":" in normalized_value
            or "@" in normalized_value
            or any(char.isspace() for char in normalized_value)
        )

    def has_valid_email_address(self, value):
        _, address = parseaddr(str(value))

        if not address:
            return False

        try:
            validate_email(address)
        except ValidationError:
            return False

        return True

    def has_reserved_email_domain(self, value):
        _, address = parseaddr(str(value))
        _, domain = address.rsplit("@", 1)

        return self.is_reserved_allowed_host(domain)

    def check_contact(self, errors):
        whatsapp_number = getattr(settings, "CONTACT_WHATSAPP_NUMBER", "")

        if len(whatsapp_number) < 7:
            errors.append("CONTACT_WHATSAPP_NUMBER debe estar configurado.")
