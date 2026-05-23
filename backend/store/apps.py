"""
Archivo: apps.py
Descripcion: Configura la aplicacion store dentro del proyecto Django.
Dependencias: Django AppConfig
"""

from django.apps import AppConfig


class StoreConfig(AppConfig):
    """
    Nombre: StoreConfig
    Descripcion: Define la configuracion base de la aplicacion store.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "store"