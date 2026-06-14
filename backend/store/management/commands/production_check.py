"""
Archivo: production_check.py
Descripcion: Comando para validar configuracion minima antes de desplegar en produccion.
Dependencias: Django settings y BaseCommand
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


PLACEHOLDER_SECRET_PARTS = (
    "django-insecure",
    "cambia",
    "change-me",
    "secret-key",
)
LOCAL_ORIGINS = (
    "http://127.0.0.1",
    "http://localhost",
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
        self.check_database(errors, options["allow_sqlite"])
        self.check_cache(errors)
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

    def check_csrf(self, errors):
        trusted_origins = getattr(settings, "CSRF_TRUSTED_ORIGINS", [])

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

    def check_https(self, errors):
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

    def check_cache(self, errors):
        cache_backend = settings.CACHES["default"]["BACKEND"]

        if cache_backend in UNSAFE_CACHE_BACKENDS:
            errors.append(
                "El cache por defecto no debe ser LocMem/Dummy en produccion."
            )

    def check_admin(self, errors, warnings):
        if settings.ADMIN_URL_PATH == "admin/":
            errors.append("DJANGO_ADMIN_URL_PATH debe cambiar la ruta /admin/.")

        if not settings.ADMIN_ALLOWED_IPS:
            errors.append("DJANGO_ADMIN_ALLOWED_IPS debe restringir el admin por IP.")

        if not getattr(settings, "TRUST_X_FORWARDED_FOR", False):
            warnings.append(
                "DJANGO_TRUST_X_FORWARDED_FOR esta desactivado; activalo solo si tu proxy limpia esa cabecera."
            )

    def check_email(self, errors, warnings):
        email_backend = getattr(settings, "EMAIL_BACKEND", "")

        if email_backend in UNSAFE_EMAIL_BACKENDS:
            errors.append("DJANGO_EMAIL_BACKEND debe ser un backend real de correo.")

        if email_backend == "django.core.mail.backends.smtp.EmailBackend":
            if not getattr(settings, "EMAIL_HOST", ""):
                errors.append("DJANGO_EMAIL_HOST debe estar configurado para SMTP.")

            if settings.EMAIL_USE_TLS and settings.EMAIL_USE_SSL:
                errors.append(
                    "DJANGO_EMAIL_USE_TLS y DJANGO_EMAIL_USE_SSL no pueden estar activos al mismo tiempo."
                )

        default_from = getattr(settings, "DEFAULT_FROM_EMAIL", "")
        notification_email = getattr(settings, "CONTACT_NOTIFICATION_EMAIL", "")
        order_notification_email = getattr(settings, "ORDER_NOTIFICATION_EMAIL", "")

        if "vape-shop.local" in default_from:
            errors.append("DEFAULT_FROM_EMAIL no debe usar vape-shop.local.")

        if "vape-shop.local" in notification_email:
            errors.append("CONTACT_NOTIFICATION_EMAIL no debe usar vape-shop.local.")

        if "vape-shop.local" in order_notification_email:
            errors.append("ORDER_NOTIFICATION_EMAIL no debe usar vape-shop.local.")

        if not default_from:
            warnings.append("DEFAULT_FROM_EMAIL esta vacio.")

        if not notification_email:
            warnings.append("CONTACT_NOTIFICATION_EMAIL esta vacio.")

        if not order_notification_email:
            warnings.append("ORDER_NOTIFICATION_EMAIL esta vacio.")

    def check_contact(self, errors):
        whatsapp_number = getattr(settings, "CONTACT_WHATSAPP_NUMBER", "")

        if len(whatsapp_number) < 7:
            errors.append("CONTACT_WHATSAPP_NUMBER debe estar configurado.")
