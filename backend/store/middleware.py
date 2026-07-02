"""
Archivo: middleware.py
Descripcion: Define middleware propio para cabeceras de seguridad adicionales.
Dependencias: Django settings
"""

import hashlib
import logging
import re
from time import perf_counter
from uuid import uuid4

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseForbidden

from .audit import get_client_ip, log_event
from .logging_utils import reset_request_id, set_request_id


request_logger = logging.getLogger("store.request")
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,63}$")


class RequestObservabilityMiddleware:
    """
    Nombre: RequestObservabilityMiddleware
    Descripcion: Correlaciona solicitudes y registra estado y duracion sin datos sensibles.
    """

    QUIET_PATHS = (
        "/api/live/",
        "/api/health/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        received_request_id = request.headers.get("X-Request-ID", "").strip()

        if REQUEST_ID_PATTERN.fullmatch(received_request_id):
            request_id = received_request_id
        else:
            request_id = uuid4().hex

        request.request_id = request_id
        context_token = set_request_id(request_id)
        started_at = perf_counter()

        try:
            response = self.get_response(request)
            duration_ms = round((perf_counter() - started_at) * 1000, 2)
            response.headers["X-Request-ID"] = request_id
            log_level = self.get_log_level(request.path, response.status_code)
            request_logger.log(
                log_level,
                "Solicitud HTTP completada.",
                extra={
                    "method": request.method,
                    "path": request.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
            return response
        finally:
            reset_request_id(context_token)

    def get_log_level(self, path, status_code):
        if path in self.QUIET_PATHS and status_code < 400:
            return logging.DEBUG

        if status_code >= 500:
            return logging.ERROR

        if status_code >= 400:
            return logging.WARNING

        return logging.INFO


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


class CrossOriginResourcePolicyMiddleware:
    """
    Nombre: CrossOriginResourcePolicyMiddleware
    Descripcion: Impide que otros origenes reutilicen respuestas de la tienda como recursos embebidos.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        policy = getattr(settings, "CROSS_ORIGIN_RESOURCE_POLICY", "")

        if policy:
            response.headers.setdefault("Cross-Origin-Resource-Policy", policy)

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
        "/api/live/",
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
