"""
Archivo: order_status.py
Descripcion: Utilidades para registrar y serializar el historial de estados de pedidos.
Dependencias: Modelos Order y OrderStatusHistory
"""

from .models import Order, OrderStatusHistory


ORDER_STATUS_LABELS = dict(Order.STATUS_CHOICES)


def get_status_label(status):
    """
    Nombre: get_status_label
    Descripcion: Retorna la etiqueta legible de un estado de orden.
    """
    return ORDER_STATUS_LABELS.get(status, status)


def get_history_user(user):
    """
    Nombre: get_history_user
    Descripcion: Evita guardar usuarios anonimos en el historial de estados.
    """
    if user and getattr(user, "is_authenticated", False):
        return user

    return None


def record_order_status(order, previous_status="", status="", changed_by=None, note=""):
    """
    Nombre: record_order_status
    Descripcion: Crea una entrada de historial para un cambio de estado de pedido.
    """
    status = status or order.status

    return OrderStatusHistory.objects.create(
        order=order,
        previous_status=previous_status or "",
        status=status,
        changed_by=get_history_user(changed_by),
        note=note,
    )


def serialize_order_status_history(order):
    """
    Nombre: serialize_order_status_history
    Descripcion: Convierte el historial de estados de una orden a datos seguros para API.
    """
    return [
        {
            "previous_status": history.previous_status,
            "previous_status_label": get_status_label(history.previous_status),
            "status": history.status,
            "status_label": get_status_label(history.status),
            "changed_by": (
                history.changed_by.username
                if history.changed_by_id and history.changed_by
                else ""
            ),
            "note": history.note,
            "created_at": history.created_at,
        }
        for history in order.status_history.all()
    ]
