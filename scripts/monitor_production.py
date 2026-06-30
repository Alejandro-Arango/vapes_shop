#!/usr/bin/env python3
"""
Verifica readiness desde fuera del despliegue y notifica fallos por webhook.
Usa solo la biblioteca estandar para ejecutarse en CI o cron sin dependencias.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4


MAX_RESPONSE_BYTES = 64 * 1024
USER_AGENT = "vapes-shop-production-monitor/1.0"


class MonitorError(RuntimeError):
    """Error esperado durante una comprobacion operativa."""


class NoRedirectHandler(HTTPRedirectHandler):
    """Evita seguir redirecciones y reenviar tokens a otro destino."""

    def redirect_request(
        self,
        request,
        file_pointer,
        code,
        message,
        headers,
        new_url,
    ):
        return None


HTTP_OPENER = build_opener(NoRedirectHandler)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00",
        "Z",
    )


def validate_url(value, label, allow_http=False):
    parsed = urlsplit(value)
    allowed_schemes = {"https"}

    if allow_http:
        allowed_schemes.add("http")

    if parsed.scheme not in allowed_schemes:
        raise MonitorError(f"{label} debe usar HTTPS.")

    if not parsed.hostname:
        raise MonitorError(f"{label} debe incluir un host valido.")

    if parsed.username or parsed.password:
        raise MonitorError(f"{label} no debe incluir credenciales.")

    if parsed.query or parsed.fragment:
        raise MonitorError(f"{label} no debe incluir query string ni fragmento.")

    return value


def safe_url(value):
    parsed = urlsplit(value)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def read_limited(response):
    body = response.read(MAX_RESPONSE_BYTES + 1)

    if len(body) > MAX_RESPONSE_BYTES:
        raise MonitorError("La respuesta supera el limite permitido.")

    return body


def write_report(path, event):
    if not path:
        return

    output_path = Path(os.path.abspath(os.fspath(path)))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(f"{output_path.suffix}.tmp")

    if (
        output_path.is_symlink()
        or output_path.parent.is_symlink()
        or temporary_path.is_symlink()
    ):
        raise MonitorError(
            "El reporte de monitoreo productivo no admite enlaces simbolicos."
        )

    temporary_path.write_text(
        json.dumps(event, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary_path, 0o600)
    os.replace(temporary_path, output_path)


def check_readiness(target_url, timeout):
    monitor_request_id = f"monitor-{uuid4().hex}"
    request = Request(
        target_url,
        headers={
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
            "X-Request-ID": monitor_request_id,
        },
        method="GET",
    )

    try:
        with HTTP_OPENER.open(request, timeout=timeout) as response:
            status_code = response.status
            body = read_limited(response)
            request_id = response.headers.get(
                "X-Request-ID",
                monitor_request_id,
            )
    except HTTPError as exc:
        request_id = exc.headers.get("X-Request-ID", monitor_request_id)
        raise MonitorError(
            f"Readiness respondio HTTP {exc.code}; request_id={request_id}."
        ) from exc
    except (TimeoutError, URLError, OSError) as exc:
        raise MonitorError(
            f"No fue posible conectar con readiness: {exc.__class__.__name__}."
        ) from exc

    if status_code != 200:
        raise MonitorError(
            f"Readiness respondio HTTP {status_code}; request_id={request_id}."
        )

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MonitorError(
            f"Readiness no devolvio JSON valido; request_id={request_id}."
        ) from exc

    expected_values = {
        "status": "ok",
        "database": "available",
        "cache": "available",
    }

    if not isinstance(payload, dict):
        raise MonitorError(
            f"Readiness devolvio una estructura invalida; request_id={request_id}."
        )

    invalid_fields = [
        field_name
        for field_name, expected_value in expected_values.items()
        if payload.get(field_name) != expected_value
    ]

    if invalid_fields:
        fields = ", ".join(invalid_fields)
        raise MonitorError(
            f"Readiness reporto campos no saludables: {fields}; "
            f"request_id={request_id}."
        )

    return {
        "request_id": request_id,
        "details": payload,
    }


def send_webhook(webhook_url, token, event, timeout):
    summary = (
        f"[CRITICAL] Vape Shop no esta listo: {event['error']} "
        f"({event['target']})"
    )
    payload = json.dumps(
        {
            "text": summary,
            "content": summary,
            "event": event,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }

    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = Request(
        webhook_url,
        data=payload,
        headers=headers,
        method="POST",
    )

    try:
        with HTTP_OPENER.open(request, timeout=timeout) as response:
            read_limited(response)
    except HTTPError as exc:
        raise MonitorError(
            f"El webhook respondio HTTP {exc.code}."
        ) from exc
    except (TimeoutError, URLError, OSError) as exc:
        raise MonitorError(
            f"No fue posible enviar el webhook: {exc.__class__.__name__}."
        ) from exc


def run_monitor(
    target_url,
    attempts=3,
    retry_delay=5,
    timeout=10,
    webhook_url="",
    webhook_token="",
    allow_http=False,
):
    if attempts < 1:
        raise MonitorError("attempts debe ser mayor o igual a 1.")

    if retry_delay < 0:
        raise MonitorError("retry_delay debe ser mayor o igual a 0.")

    if timeout < 1:
        raise MonitorError("timeout debe ser mayor o igual a 1.")

    target_url = validate_url(
        target_url,
        "PRODUCTION_HEALTH_URL",
        allow_http=allow_http,
    )

    if webhook_url:
        webhook_url = validate_url(
            webhook_url,
            "MONITOR_WEBHOOK_URL",
            allow_http=allow_http,
        )

    errors = []

    for attempt in range(1, attempts + 1):
        try:
            result = check_readiness(target_url, timeout)
            return 0, {
                "event": "production_readiness",
                "status": "ok",
                "checked_at": utc_now(),
                "target": safe_url(target_url),
                "attempt": attempt,
                **result,
            }
        except MonitorError as exc:
            errors.append(str(exc))

            if attempt < attempts:
                time.sleep(retry_delay)

    event = {
        "event": "production_readiness",
        "status": "critical",
        "checked_at": utc_now(),
        "target": safe_url(target_url),
        "attempts": attempts,
        "error": errors[-1],
        "errors": errors,
    }

    if webhook_url:
        try:
            send_webhook(
                webhook_url,
                webhook_token,
                event,
                timeout,
            )
            event["alert"] = "sent"
        except MonitorError as exc:
            event["alert"] = "failed"
            event["alert_error"] = str(exc)
    else:
        event["alert"] = "not_configured"

    return 1, event


def positive_integer(value):
    parsed = int(value)

    if parsed < 1:
        raise argparse.ArgumentTypeError("debe ser mayor o igual a 1")

    return parsed


def non_negative_number(value):
    parsed = float(value)

    if parsed < 0:
        raise argparse.ArgumentTypeError("debe ser mayor o igual a 0")

    return parsed


def build_parser():
    parser = argparse.ArgumentParser(
        description="Verifica el readiness productivo y alerta por webhook.",
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("PRODUCTION_HEALTH_URL", ""),
        help="URL HTTPS del endpoint /healthz.",
    )
    parser.add_argument(
        "--attempts",
        type=positive_integer,
        default=3,
    )
    parser.add_argument(
        "--retry-delay",
        type=non_negative_number,
        default=5,
    )
    parser.add_argument(
        "--timeout",
        type=positive_integer,
        default=10,
    )
    parser.add_argument(
        "--webhook-url",
        default=os.environ.get("MONITOR_WEBHOOK_URL", ""),
    )
    parser.add_argument(
        "--webhook-token",
        default=os.environ.get("MONITOR_WEBHOOK_TOKEN", ""),
    )
    parser.add_argument(
        "--output",
        default=os.environ.get("MONITOR_REPORT_PATH", ""),
        help="Ruta opcional para guardar el reporte JSON del monitoreo.",
    )
    parser.add_argument(
        "--allow-http",
        action="store_true",
        help="Permite HTTP solo para pruebas locales.",
    )
    return parser


def main():
    parser = build_parser()
    arguments = parser.parse_args()

    if not arguments.url:
        parser.error(
            "define --url o la variable PRODUCTION_HEALTH_URL"
        )

    try:
        exit_code, event = run_monitor(
            target_url=arguments.url,
            attempts=arguments.attempts,
            retry_delay=arguments.retry_delay,
            timeout=arguments.timeout,
            webhook_url=arguments.webhook_url,
            webhook_token=arguments.webhook_token,
            allow_http=arguments.allow_http,
        )
    except (MonitorError, ValueError) as exc:
        event = {
            "event": "production_readiness",
            "status": "configuration_error",
            "checked_at": utc_now(),
            "error": str(exc),
        }
        exit_code = 2

    try:
        write_report(arguments.output, event)
    except (MonitorError, ValueError) as exc:
        event["report_error"] = str(exc)
        if exit_code == 0:
            exit_code = 2

    output = json.dumps(
        event,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    print(output, file=sys.stdout if exit_code == 0 else sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
