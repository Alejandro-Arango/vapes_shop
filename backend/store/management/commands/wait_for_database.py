"""
Archivo: wait_for_database.py
Descripcion: Espera de forma acotada a que la base de datos acepte conexiones.
Dependencias: Django database y BaseCommand
"""

import time

from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError, connection


class Command(BaseCommand):
    help = "Espera a que la base de datos este disponible."

    def add_arguments(self, parser):
        parser.add_argument("--attempts", type=int, default=30)
        parser.add_argument("--delay", type=float, default=2.0)

    def handle(self, *args, **options):
        attempts = options["attempts"]
        delay = options["delay"]

        if attempts < 1:
            raise CommandError("--attempts debe ser mayor o igual a 1.")

        if delay < 0:
            raise CommandError("--delay no puede ser negativo.")

        for attempt in range(1, attempts + 1):
            try:
                connection.ensure_connection()
            except OperationalError as exc:
                connection.close()

                if attempt == attempts:
                    raise CommandError(
                        "La base de datos no estuvo disponible a tiempo."
                    ) from exc

                self.stdout.write(
                    f"Base de datos no disponible ({attempt}/{attempts}); reintentando."
                )
                time.sleep(delay)
            else:
                self.stdout.write(
                    self.style.SUCCESS("Base de datos disponible.")
                )
                return
