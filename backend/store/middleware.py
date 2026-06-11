"""
Archivo: middleware.py
Descripcion: Define middleware propio para cabeceras de seguridad adicionales.
Dependencias: Django settings
"""

from django.conf import settings


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


class SensitiveApiCacheControlMiddleware:
    """
    Nombre: SensitiveApiCacheControlMiddleware
    Descripcion: Evita cachear respuestas de API que pueden contener datos de usuario.
    """

    SENSITIVE_API_PREFIXES = (
        "/api/auth/",
        "/api/cart/",
        "/api/contact/",
        "/api/orders/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.path.startswith(self.SENSITIVE_API_PREFIXES):
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        return response
