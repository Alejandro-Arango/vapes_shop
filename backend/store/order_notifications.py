"""
Archivo: order_notifications.py
Descripcion: Construye y envia notificaciones por correo relacionadas con pedidos.
Dependencias: Django settings, Django mail y modelos de ordenes
"""

import logging

from django.conf import settings
from django.core.mail import send_mail

from .url_utils import normalize_safe_external_url


logger = logging.getLogger(__name__)
ORDER_STATUS_NOTIFICATION_STATUSES = {"enviado", "entregado"}


def format_money(value):
    """
    Nombre: format_money
    Descripcion: Convierte valores monetarios a texto consistente para correos.
    """
    return f"${float(value or 0):.2f}"


def build_order_items_text(order):
    """
    Nombre: build_order_items_text
    Descripcion: Construye el resumen de productos incluidos en una orden.
    """
    lines = []

    for item in order.orderitem_set.select_related("product").all():
        product_name = item.display_product_name
        unit_price = item.effective_unit_price
        line_total = unit_price * item.quantity

        lines.append(
            f"- {product_name} x {item.quantity}: {format_money(line_total)}"
        )

    return "\n".join(lines) or "- Sin productos registrados"


def build_shipping_text(order):
    """
    Nombre: build_shipping_text
    Descripcion: Construye el bloque de datos de envio para correos de pedido.
    """
    return (
        f"Nombre: {order.shipping_name or 'No registrado'}\n"
        f"Telefono: {order.shipping_phone or 'No registrado'}\n"
        f"Direccion: {order.shipping_address or 'No registrada'}\n"
        f"Ciudad: {order.shipping_city or 'No registrada'}\n"
        f"Notas: {order.shipping_notes or 'Sin notas'}"
    )


def build_customer_order_message(order):
    """
    Nombre: build_customer_order_message
    Descripcion: Construye el correo de confirmacion para el cliente.
    """
    return (
        f"Hola {order.shipping_name or order.customer.first_name or 'Cliente'},\n\n"
        f"Recibimos tu pedido #{order.id} correctamente.\n\n"
        "Resumen del pedido:\n"
        f"{build_order_items_text(order)}\n\n"
        f"Subtotal: {format_money(order.subtotal_amount)}\n"
        f"Descuento: {format_money(order.discount_amount)}\n"
        f"Total: {format_money(order.total_amount)}\n\n"
        "Datos de envio:\n"
        f"{build_shipping_text(order)}\n\n"
        "Te contactaremos si necesitamos confirmar algun detalle."
    )


def build_admin_order_message(order):
    """
    Nombre: build_admin_order_message
    Descripcion: Construye el correo interno para avisar al administrador.
    """
    customer_email = order.customer.email or "No registrado"

    return (
        f"Se registro un nuevo pedido #{order.id}.\n\n"
        f"Cliente: {order.customer}\n"
        f"Correo: {customer_email}\n"
        f"Estado: {order.get_status_display()}\n\n"
        "Productos:\n"
        f"{build_order_items_text(order)}\n\n"
        f"Subtotal: {format_money(order.subtotal_amount)}\n"
        f"Descuento: {format_money(order.discount_amount)}\n"
        f"Total: {format_money(order.total_amount)}\n\n"
        "Datos de envio:\n"
        f"{build_shipping_text(order)}"
    )


def build_order_status_message(order):
    """
    Nombre: build_order_status_message
    Descripcion: Construye el correo para avisar avances relevantes del pedido.
    """
    tracking_lines = []

    if order.tracking_carrier:
        tracking_lines.append(f"Transportadora: {order.tracking_carrier}")

    if order.tracking_number:
        tracking_lines.append(f"Guia: {order.tracking_number}")

    safe_tracking_url = normalize_safe_external_url(order.tracking_url)

    if safe_tracking_url:
        tracking_lines.append(f"Rastreo: {safe_tracking_url}")

    tracking_text = "\n".join(tracking_lines) or "Aun no hay datos de rastreo registrados."

    return (
        f"Hola {order.shipping_name or order.customer.first_name or 'Cliente'},\n\n"
        f"Tu pedido #{order.id} ahora esta en estado: {order.get_status_display()}.\n\n"
        f"{tracking_text}\n\n"
        f"Total del pedido: {format_money(order.total_amount)}\n\n"
        "Gracias por comprar en Vape Shop."
    )


def send_order_email(subject, message, recipient):
    """
    Nombre: send_order_email
    Descripcion: Envia un correo de pedido a un destinatario unico.
    Retorna: True si Django confirma el envio, false si no se pudo enviar.
    """
    clean_recipient = str(recipient or "").strip()

    if not clean_recipient:
        return False

    try:
        sent_count = send_mail(
            subject=subject,
            message=message,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=[clean_recipient],
            fail_silently=False,
        )
    except Exception as exc:
        logger.warning("No se pudo enviar correo de pedido: %s", exc)
        return False

    return sent_count > 0


def notify_order_created(order):
    """
    Nombre: notify_order_created
    Descripcion: Notifica al cliente y al administrador cuando se crea un pedido.
    Retorna: Diccionario con el resultado de cada envio.
    """
    customer_email_sent = send_order_email(
        subject=f"Pedido #{order.id} recibido en Vape Shop",
        message=build_customer_order_message(order),
        recipient=order.customer.email,
    )
    admin_email = getattr(
        settings,
        "ORDER_NOTIFICATION_EMAIL",
        getattr(settings, "CONTACT_NOTIFICATION_EMAIL", ""),
    )
    admin_email_sent = send_order_email(
        subject=f"Nuevo pedido #{order.id} en Vape Shop",
        message=build_admin_order_message(order),
        recipient=admin_email,
    )

    return {
        "customer_email_sent": customer_email_sent,
        "admin_email_sent": admin_email_sent,
    }


def notify_order_status_changed(order):
    """
    Nombre: notify_order_status_changed
    Descripcion: Notifica al cliente cuando el pedido cambia a un estado relevante.
    Retorna: True si se envio correo o None si el estado no requiere notificacion.
    """
    if order.status not in ORDER_STATUS_NOTIFICATION_STATUSES:
        return None

    return send_order_email(
        subject=f"Actualizacion de pedido #{order.id}: {order.get_status_display()}",
        message=build_order_status_message(order),
        recipient=order.customer.email,
    )
