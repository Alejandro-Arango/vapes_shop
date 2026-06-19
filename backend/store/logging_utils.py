"""
Archivo: logging_utils.py
Descripcion: Agrega contexto de solicitud y salida JSON para logs operativos.
Dependencias: contextvars, datetime, json y logging
"""

import json
import logging
from contextvars import ContextVar
from datetime import datetime, timezone


request_id_context = ContextVar("request_id", default="-")


def set_request_id(request_id):
    """
    Nombre: set_request_id
    Descripcion: Asocia un identificador a los logs de la solicitud actual.
    """
    return request_id_context.set(request_id)


def reset_request_id(token):
    """
    Nombre: reset_request_id
    Descripcion: Restaura el contexto previo al terminar la solicitud.
    """
    request_id_context.reset(token)


class RequestContextFilter(logging.Filter):
    """
    Nombre: RequestContextFilter
    Descripcion: Agrega request_id a cada registro enviado por Django.
    """

    def filter(self, record):
        record.request_id = request_id_context.get()
        return True


class JsonFormatter(logging.Formatter):
    """
    Nombre: JsonFormatter
    Descripcion: Serializa logs en JSON de una linea para agregadores externos.
    """

    EXTRA_FIELDS = (
        "method",
        "path",
        "status_code",
        "duration_ms",
    )

    def format(self, record):
        payload = {
            "timestamp": datetime.fromtimestamp(
                record.created,
                tz=timezone.utc,
            ).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }

        for field_name in self.EXTRA_FIELDS:
            field_value = getattr(record, field_name, None)

            if field_value is not None:
                payload[field_name] = field_value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        )
