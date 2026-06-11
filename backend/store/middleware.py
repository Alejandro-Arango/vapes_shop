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
