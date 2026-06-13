"""
Archivo: middleware.py
Descripcion: Define middleware propio para cabeceras de seguridad adicionales.
Dependencias: Django settings
"""

from django.conf import settings
from django.http import HttpResponseForbidden

from .audit import get_client_ip


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
