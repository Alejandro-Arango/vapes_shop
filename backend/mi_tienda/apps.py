"""
Archivo: apps.py
Descripcion: Sustituye el AdminSite predeterminado por el sitio protegido con OTP.
Dependencias: Django AdminConfig
"""

from django.contrib.admin.apps import AdminConfig


class StoreAdminConfig(AdminConfig):
    default_site = "mi_tienda.admin.StoreOTPAdminSite"
