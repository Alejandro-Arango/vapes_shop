"""
Archivo: audit.py
Descripcion: Utilidades para registrar eventos relevantes sin interrumpir el flujo principal.
Dependencias: logging y modelo EventLog
"""

import logging

from django.db import DatabaseError

from .models import EventLog


logger = logging.getLogger(__name__)


def get_client_ip(request):
    """
    Nombre: get_client_ip
    Descripcion: Obtiene una IP probable del request usando cabeceras comunes.
    Retorna: IP o None.
    """
    if not request:
        return None

    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")

    if forwarded_for:
        return forwarded_for.split(",")[0].strip() or None

    return request.META.get("REMOTE_ADDR")


def get_request_user(request, explicit_user=None):
    """
    Nombre: get_request_user
    Descripcion: Resuelve el usuario autenticado que se asociara al evento.
    Retorna: Usuario o None.
    """
    if explicit_user:
        return explicit_user

    if not request:
        return None

    user = getattr(request, "user", None)

    if user and user.is_authenticated:
        return user

    return None


def log_event(event_type, message, request=None, user=None, severity="info", metadata=None):
    """
    Nombre: log_event
    Descripcion: Registra un evento en base de datos y consola sin romper la accion principal.
    Retorna: EventLog creado o None si no fue posible guardar.
    """
    metadata = metadata or {}
    resolved_user = get_request_user(request, explicit_user=user)
    path = getattr(request, "path", "") if request else ""
    user_agent = ""

    if request:
        user_agent = request.META.get("HTTP_USER_AGENT", "")

    try:
        event = EventLog.objects.create(
            event_type=event_type[:80],
            severity=severity,
            user=resolved_user,
            message=message[:255],
            path=path[:255],
            ip_address=get_client_ip(request),
            user_agent=user_agent[:255],
            metadata=metadata,
        )
    except (DatabaseError, ValueError) as exc:
        logger.warning("No se pudo registrar EventLog %s: %s", event_type, exc)
        return None

    logger.info("Evento registrado: %s", event_type)

    return event
