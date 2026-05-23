"""
Archivo: urls.py
Descripcion: Define las rutas principales del proyecto Django, incluyendo panel administrativo, rutas de la app store y archivos media en desarrollo.
Dependencias: Django admin, include, path, settings y static
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("store.urls")),
]


if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )