"""
Archivo: context_processors.py
Descripcion: Expone valores de configuracion seguros a las plantillas.
Dependencias: settings de Django
"""

from django.conf import settings


def store_settings(request):
    """
    Nombre: store_settings
    Descripcion: Publica ajustes publicos de la tienda para usarlos en plantillas
    sin codificarlos a mano (por ejemplo el numero de contacto de WhatsApp).
    """
    return {
        "contact_whatsapp_number": getattr(
            settings,
            "CONTACT_WHATSAPP_NUMBER",
            "",
        ),
    }
