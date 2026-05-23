#!/usr/bin/env python
"""
Archivo: manage.py
Descripcion: Punto de entrada para ejecutar comandos administrativos del proyecto Django.
Dependencias: os, sys y django.core.management
"""

import os
import sys


def main():
    """
    Nombre: main
    Descripcion: Configura el entorno de Django y ejecuta comandos administrativos desde la terminal.
    """
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mi_tienda.settings")

    try:
        from django.core.management import execute_from_command_line

    except ImportError as exc:
        raise ImportError(
            "No se pudo importar Django. Verifica que este instalado, "
            "que el entorno virtual este activo y que PYTHONPATH este configurado."
        ) from exc

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()