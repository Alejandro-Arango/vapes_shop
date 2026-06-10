"""
Archivo: throttles.py
Descripcion: Define limites basicos de uso para reducir abuso en endpoints sensibles.
Dependencias: Django REST Framework throttling
"""

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class AuthAnonRateThrottle(AnonRateThrottle):
    """
    Nombre: AuthAnonRateThrottle
    Descripcion: Limita intentos anonimos sobre registro e inicio de sesion.
    """

    scope = "auth_anon"


class ContactAnonRateThrottle(AnonRateThrottle):
    """
    Nombre: ContactAnonRateThrottle
    Descripcion: Limita envios anonimos del formulario de contacto.
    """

    scope = "contact_anon"


class CheckoutUserRateThrottle(UserRateThrottle):
    """
    Nombre: CheckoutUserRateThrottle
    Descripcion: Limita confirmaciones de compra por usuario autenticado.
    """

    scope = "checkout_user"
