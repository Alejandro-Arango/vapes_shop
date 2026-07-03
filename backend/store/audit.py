"""
Archivo: audit.py
Descripcion: Utilidades para registrar eventos relevantes sin interrumpir el flujo principal.
Dependencias: logging y modelo EventLog
"""

import logging
from ipaddress import ip_address

from django.conf import settings
from django.db import DatabaseError

from .models import EventLog


logger = logging.getLogger(__name__)


SENSITIVE_METADATA_KEYS = (
    "password",
    "token",
    "secret",
    "authorization",
    "api_key",
    "cookie",
    "csrf",
    "session",
)
REDACTED_VALUE = "[redacted]"


def normalize_ip_address(value):
    """
    Nombre: normalize_ip_address
    Descripcion: Valida una IP antes de guardarla en auditoria.
    Retorna: IP normalizada o None si el valor no es valido.
    """
    if not value:
        return None

    try:
        return str(ip_address(str(value).strip()))
    except ValueError:
        return None


def sanitize_metadata(value):
    """
    Nombre: sanitize_metadata
    Descripcion: Redacta valores sensibles antes de guardarlos en auditoria.
    Retorna: Metadata segura para almacenar en EventLog.
    """
    if isinstance(value, dict):
        sanitized = {}

        for key, item in value.items():
            key_text = str(key)

            has_sensitive_key = any(
                secret_key in key_text.lower()
                for secret_key in SENSITIVE_METADATA_KEYS
            )

            if has_sensitive_key:
                sanitized[key_text] = REDACTED_VALUE
            else:
                sanitized[key_text] = sanitize_metadata(item)

        return sanitized

    if isinstance(value, (list, tuple)):
        return [
            sanitize_metadata(item)
            for item in value
        ]

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    return str(value)


def get_client_ip(request):
    """
    Nombre: get_client_ip
    Descripcion: Obtiene una IP probable del request usando cabeceras comunes.
    Retorna: IP o None.
    """
    if not request:
        return None

    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")

    if getattr(settings, "TRUST_X_FORWARDED_FOR", False) and forwarded_for:
        return normalize_ip_address(forwarded_for.split(",")[0])

    return normalize_ip_address(request.META.get("REMOTE_ADDR"))


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
    metadata = sanitize_metadata(metadata or {})
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
