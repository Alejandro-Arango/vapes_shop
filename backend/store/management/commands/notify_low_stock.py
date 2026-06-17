"""
Archivo: notify_low_stock.py
Descripcion: Comando operativo para reportar productos activos con bajo stock.
Dependencias: Django settings, mail, BaseCommand, auditoria y modelo Product
"""

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError

from store.audit import log_event
from store.models import Product


DEFAULT_STOCK_THRESHOLD = 3


def get_low_stock_products(threshold):
    """
    Nombre: get_low_stock_products
    Descripcion: Obtiene productos activos con stock menor o igual al umbral.
    """
    return (
        Product.objects
        .filter(is_active=True, stock__lte=threshold)
        .order_by("stock", "name", "id")
    )


def build_low_stock_message(products, threshold):
    """
    Nombre: build_low_stock_message
    Descripcion: Construye el contenido del reporte de inventario.
    """
    lines = [
        "Reporte de inventario bajo en Vape Shop.",
        "",
        f"Umbral configurado: {threshold} unidad(es).",
        f"Productos encontrados: {len(products)}.",
        "",
    ]

    if not products:
        lines.append("No hay productos activos con bajo stock.")
        return "\n".join(lines)

    lines.append("Productos:")

    for product in products:
        status = "Sin stock" if product.stock == 0 else f"Stock: {product.stock}"
        lines.append(f"- #{product.id} {product.name}: {status}")

    return "\n".join(lines)


def get_inventory_recipient():
    """
    Nombre: get_inventory_recipient
    Descripcion: Obtiene el correo operativo para alertas de inventario.
    """
    return str(
        getattr(
            settings,
            "INVENTORY_NOTIFICATION_EMAIL",
            getattr(settings, "ORDER_NOTIFICATION_EMAIL", ""),
        )
        or ""
    ).strip()


class Command(BaseCommand):
    """
    Nombre: Command
    Descripcion: Reporta inventario bajo y envia alerta opcional por correo.
    """

    help = "Reportar productos activos con bajo stock."

    def add_arguments(self, parser):
        parser.add_argument(
            "--threshold",
            type=int,
            default=DEFAULT_STOCK_THRESHOLD,
            help=f"Umbral de stock bajo. Valor por defecto: {DEFAULT_STOCK_THRESHOLD}.",
        )
        parser.add_argument(
            "--send-email",
            action="store_true",
            help="Envia el reporte al correo de inventario configurado.",
        )

    def handle(self, *args, **options):
        threshold = options["threshold"]

        if threshold < 0:
            raise CommandError("--threshold debe ser mayor o igual a 0.")

        products = list(get_low_stock_products(threshold))
        message = build_low_stock_message(products, threshold)
        product_count = len(products)

        if not options["send_email"]:
            self.stdout.write(message)
            self.stdout.write(
                self.style.WARNING(
                    "Simulacion: usa --send-email para enviar este reporte."
                )
            )
            return

        recipient = get_inventory_recipient()

        if not recipient:
            raise CommandError(
                "INVENTORY_NOTIFICATION_EMAIL u ORDER_NOTIFICATION_EMAIL debe estar configurado."
            )

        try:
            sent_count = send_mail(
                subject=f"Alerta de inventario Vape Shop ({product_count} producto(s))",
                message=message,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=[recipient],
                fail_silently=False,
            )
        except Exception as exc:
            raise CommandError(
                f"No se pudo enviar la alerta de inventario: {exc.__class__.__name__}"
            ) from exc

        email_sent = sent_count > 0

        log_event(
            "inventory_low_stock_report",
            "Reporte de inventario bajo enviado.",
            severity="warning" if product_count else "info",
            metadata={
                "threshold": threshold,
                "product_count": product_count,
                "product_ids": [product.id for product in products[:20]],
                "product_ids_truncated": product_count > 20,
                "email_sent": email_sent,
            },
        )

        self.stdout.write(message)
        self.stdout.write(
            self.style.SUCCESS(
                f"Reporte enviado a {recipient}: {product_count} producto(s)."
            )
        )
