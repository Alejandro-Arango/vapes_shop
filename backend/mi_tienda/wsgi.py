"""
Archivo: wsgi.py
Descripcion: Expone la aplicacion WSGI del proyecto Django para servidores web compatibles con ejecucion sincrona.
Dependencias: os y django.core.wsgi
"""

import os

from django.core.wsgi import get_wsgi_application


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mi_tienda.settings")

application = get_wsgi_application()