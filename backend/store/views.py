"""
Archivo: views.py
Descripcion: Define la vista principal que renderiza la interfaz completa de la tienda.
Dependencias: Django render
"""

from django.shortcuts import render


def home(request):
    """
    Nombre: home
    Descripcion: Renderiza la plantilla principal que contiene el frontend de la aplicacion.
    """
    return render(request, "store/home.html")