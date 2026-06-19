"""
Archivo: middleware.py
Descripcion: Define middleware propio para cabeceras de seguridad adicionales.
Dependencias: Django settings
"""

import hashlib

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseForbidden

from .audit import get_client_ip, log_event


class AdminAccessMiddleware:
    """
    Nombre: AdminAccessMiddleware
    Descripcion: Restringe el panel administrativo por IP cuando existe allowlist configurada.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        admin_path = f"/{settings.ADMIN_URL_PATH}"
        allowed_ips = getattr(settings, "ADMIN_ALLOWED_IPS", ())

        if allowed_ips and request.path_info.startswith(admin_path):
            client_ip = get_client_ip(request)

            if client_ip not in allowed_ips:
                return HttpResponseForbidden("Acceso no permitido.")

        return self.get_response(request)


def is_admin_path(request):
    admin_path = f"/{settings.ADMIN_URL_PATH}"

    return request.path_info.startswith(admin_path)


def is_admin_login_path(request):
    admin_path = f"/{settings.ADMIN_URL_PATH}".rstrip("/")
    request_path = request.path_info.rstrip("/")

    return request_path in (admin_path, f"{admin_path}/login")


def is_otp_verified(user):
    verifier = getattr(user, "is_verified", None)

    if callable(verifier):
        return verifier()

    return getattr(user, "otp_device", None) is not None


class AdminSessionSecurityMiddleware:
    """
    Nombre: AdminSessionSecurityMiddleware
    Descripcion: Limita la sesion verificada del admin y evita cachear sus respuestas.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        admin_request = is_admin_path(request)
        user = getattr(request, "user", None)

        if (
            admin_request
            and user
            and user.is_authenticated
            and is_otp_verified(user)
        ):
            request.session.set_expiry(settings.ADMIN_SESSION_COOKIE_AGE)

        response = self.get_response(request)

        if admin_request:
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        return response


class AdminLoginThrottleMiddleware:
    """
    Nombre: AdminLoginThrottleMiddleware
    Descripcion: Bloquea temporalmente combinaciones de IP y usuario tras fallos repetidos.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method != "POST" or not is_admin_login_path(request):
            return self.get_response(request)

        identifier = str(request.POST.get("username") or "").strip().lower()
        client_ip = get_client_ip(request) or "unknown"
        cache_suffix = hashlib.sha256(
            f"{client_ip}|{identifier}".encode("utf-8")
        ).hexdigest()
        attempts_key = f"store:admin-login-attempts:{cache_suffix}"
        lock_key = f"store:admin-login-lock:{cache_suffix}"
        lockout_seconds = settings.ADMIN_LOGIN_LOCKOUT_SECONDS

        if cache.get(lock_key):
            response = HttpResponse(
                "Demasiados intentos. Intenta de nuevo mas tarde.",
                status=429,
            )
            response.headers["Retry-After"] = str(lockout_seconds)
            return response

        response = self.get_response(request)
        user = getattr(request, "user", None)
        login_succeeded = (
            response.status_code in (301, 302, 303)
            and user
            and user.is_authenticated
            and is_otp_verified(user)
        )

        if login_succeeded:
            cache.delete_many((attempts_key, lock_key))
            return response

        attempts = int(cache.get(attempts_key, 0)) + 1
        cache.set(attempts_key, attempts, timeout=lockout_seconds)

        if attempts >= settings.ADMIN_LOGIN_MAX_ATTEMPTS:
            cache.set(lock_key, True, timeout=lockout_seconds)
            log_event(
                "admin_login_locked",
                "Acceso administrativo bloqueado temporalmente por intentos fallidos.",
                request=request,
                severity="warning",
                metadata={"attempts": attempts},
            )

        return response


class PermissionsPolicyMiddleware:
    """
    Nombre: PermissionsPolicyMiddleware
    Descripcion: Agrega Permissions-Policy para limitar capacidades del navegador que la tienda no necesita.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        policy = getattr(settings, "PERMISSIONS_POLICY", "")

        if policy:
            response.headers.setdefault("Permissions-Policy", policy)

        return response


class ContentSecurityPolicyMiddleware:
    """
    Nombre: ContentSecurityPolicyMiddleware
    Descripcion: Restringe los origenes permitidos para scripts, estilos y otros recursos del navegador.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        policy = getattr(settings, "CONTENT_SECURITY_POLICY", "")

        if policy:
            response.headers.setdefault("Content-Security-Policy", policy)

        return response


class ApiCacheControlMiddleware:
    """
    Nombre: ApiCacheControlMiddleware
    Descripcion: Evita cachear respuestas de API sensibles o que deben reflejar estado actual.
    """

    NO_CACHE_API_PREFIXES = (
        "/api/auth/",
        "/api/cart/",
        "/api/contact/",
        "/api/favorites/",
        "/api/health/",
        "/api/orders/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.path.startswith(self.NO_CACHE_API_PREFIXES):
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        return response
