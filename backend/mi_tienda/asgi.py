"""
Archivo: asgi.py
Descripcion: Expone la aplicacion ASGI del proyecto Django para servidores compatibles con comunicacion asincrona.
Dependencias: os y django.core.asgi
"""

import os

from django.core.asgi import get_asgi_application


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mi_tienda.settings")

application = get_asgi_application()