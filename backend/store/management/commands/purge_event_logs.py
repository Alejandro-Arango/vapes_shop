"""
Archivo: purge_event_logs.py
Descripcion: Comando de mantenimiento para purgar eventos operativos antiguos.
Dependencias: Django BaseCommand, timezone y modelo EventLog
"""

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from store.audit import log_event
from store.models import EventLog


DEFAULT_RETENTION_DAYS = 180


class Command(BaseCommand):
    """
    Nombre: Command
    Descripcion: Elimina eventos antiguos de auditoria con confirmacion explicita.
    """

    help = "Purgar EventLog antiguos con modo simulacion por defecto."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=DEFAULT_RETENTION_DAYS,
            help=f"Dias de retencion. Valor por defecto: {DEFAULT_RETENTION_DAYS}.",
        )
        parser.add_argument(
            "--severity",
            choices=[severity for severity, _ in EventLog.SEVERITY_CHOICES],
            default="",
            help="Filtra por severidad exacta antes de purgar.",
        )
        parser.add_argument(
            "--event-type",
            default="",
            help="Filtra por tipo de evento exacto antes de purgar.",
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Ejecuta el borrado. Sin esta bandera solo simula el resultado.",
        )

    def handle(self, *args, **options):
        days = options["days"]

        if days < 1:
            raise CommandError("--days debe ser un entero mayor o igual a 1.")

        severity = str(options.get("severity") or "").strip()
        event_type = str(options.get("event_type") or "").strip()
        cutoff = timezone.now() - timedelta(days=days)
        events = EventLog.objects.filter(created_at__lt=cutoff)

        if severity:
            events = events.filter(severity=severity)

        if event_type:
            events = events.filter(event_type=event_type)

        candidates_count = events.count()

        if not options["confirm"]:
            self.stdout.write(
                self.style.WARNING(
                    f"Simulacion: {candidates_count} evento(s) serian eliminados. "
                    "Usa --confirm para ejecutar el borrado."
                )
            )
            return

        deleted_count, _ = events.delete()

        log_event(
            "event_log_purge_completed",
            "Purgado de eventos antiguos ejecutado.",
            metadata={
                "days": days,
                "cutoff": cutoff.isoformat(),
                "deleted_count": deleted_count,
                "severity": severity,
                "event_type": event_type,
            },
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Purgado completado: {deleted_count} evento(s) eliminado(s)."
            )
        )
