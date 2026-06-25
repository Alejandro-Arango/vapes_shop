#!/usr/bin/env python3
"""
Verifica que una caida de MySQL degrade readiness sin perder liveness.
Usa solo la biblioteca estandar para ejecutarse dentro de CI.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request

SCRIPT_DIRECTORY = Path(__file__).resolve().parent

if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

from monitor_production import (
    HTTP_OPENER,
    MonitorError,
    read_limited,
    safe_url,
    validate_url,
)


def request_endpoint(target_url, timeout, accept):
    request = Request(
        target_url,
        headers={"Accept": accept},
        method="GET",
    )

    try:
        with HTTP_OPENER.open(request, timeout=timeout) as response:
            return (
                response.status,
                read_limited(response),
                response.headers.get("X-Request-ID", ""),
            )
    except HTTPError as exc:
        return (
            exc.code,
            read_limited(exc),
            exc.headers.get("X-Request-ID", ""),
        )
    except (TimeoutError, URLError, OSError) as exc:
        raise MonitorError(
            f"No fue posible conectar con {safe_url(target_url)}: "
            f"{exc.__class__.__name__}."
        ) from exc


def check_liveness(target_url, timeout):
    status_code, body, request_id = request_endpoint(
        target_url,
        timeout,
        "text/plain, application/json",
    )

    if status_code != 200:
        raise MonitorError(
            f"Liveness respondio HTTP {status_code}; "
            f"request_id={request_id or 'not-provided'}."
        )

    if not body.strip():
        raise MonitorError(
            f"Liveness devolvio una respuesta vacia; "
            f"request_id={request_id or 'not-provided'}."
        )

    return {"request_id": request_id}


def check_database_outage(target_url, timeout):
    status_code, body, request_id = request_endpoint(
        target_url,
        timeout,
        "application/json",
    )

    if status_code != 503:
        raise MonitorError(
            f"Readiness debia responder HTTP 503 y respondio {status_code}; "
            f"request_id={request_id or 'not-provided'}."
        )

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MonitorError(
            f"Readiness degradado no devolvio JSON valido; "
            f"request_id={request_id or 'not-provided'}."
        ) from exc

    expected_values = {
        "status": "error",
        "database": "unavailable",
        "cache": "not_checked",
    }
    invalid_fields = [
        field_name
        for field_name, expected_value in expected_values.items()
        if not isinstance(payload, dict)
        or payload.get(field_name) != expected_value
    ]

    if invalid_fields:
        fields = ", ".join(invalid_fields)
        raise MonitorError(
            f"Readiness no identifico la caida de base de datos: {fields}; "
            f"request_id={request_id or 'not-provided'}."
        )

    return {
        "request_id": request_id,
        "details": payload,
    }


def verify_database_outage(
    liveness_url,
    readiness_url,
    budget=20,
    interval=1,
    timeout=5,
    consecutive=2,
    allow_http=False,
    sleep=time.sleep,
    monotonic=time.monotonic,
):
    if budget <= 0:
        raise MonitorError("budget debe ser mayor que 0.")

    if interval < 0:
        raise MonitorError("interval debe ser mayor o igual a 0.")

    if timeout < 1:
        raise MonitorError("timeout debe ser mayor o igual a 1.")

    if consecutive < 1:
        raise MonitorError("consecutive debe ser mayor o igual a 1.")

    liveness_url = validate_url(
        liveness_url,
        "OUTAGE_LIVENESS_URL",
        allow_http=allow_http,
    )
    readiness_url = validate_url(
        readiness_url,
        "OUTAGE_READINESS_URL",
        allow_http=allow_http,
    )
    started_at = monotonic()
    attempts = 0
    consecutive_successes = 0
    errors = []
    request_ids = []

    while monotonic() - started_at <= budget:
        attempts += 1

        try:
            liveness = check_liveness(liveness_url, timeout)
            readiness = check_database_outage(readiness_url, timeout)
            consecutive_successes += 1
            request_ids.append(
                {
                    "liveness": liveness["request_id"],
                    "readiness": readiness["request_id"],
                }
            )

            if consecutive_successes >= consecutive:
                elapsed = monotonic() - started_at
                return 0, {
                    "event": "database_outage",
                    "status": "degraded_as_expected",
                    "elapsed_seconds": round(elapsed, 3),
                    "attempts": attempts,
                    "consecutive_successes": consecutive_successes,
                    "liveness_target": safe_url(liveness_url),
                    "readiness_target": safe_url(readiness_url),
                    "request_ids": request_ids[-consecutive:],
                    "errors": errors,
                }
        except MonitorError as exc:
            consecutive_successes = 0
            errors.append(str(exc))

        if monotonic() - started_at <= budget:
            sleep(interval)

    elapsed = monotonic() - started_at
    return 1, {
        "event": "database_outage",
        "status": "timeout",
        "elapsed_seconds": round(elapsed, 3),
        "attempts": attempts,
        "consecutive_successes": consecutive_successes,
        "liveness_target": safe_url(liveness_url),
        "readiness_target": safe_url(readiness_url),
        "errors": errors,
    }


def write_report(path, report):
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
            "El reporte de dependencia no admite enlaces simbolicos."
        )

    temporary_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary_path, 0o600)
    os.replace(temporary_path, output_path)


def positive_float(value):
    parsed = float(value)

    if parsed <= 0:
        raise argparse.ArgumentTypeError("debe ser mayor que 0")

    return parsed


def non_negative_float(value):
    parsed = float(value)

    if parsed < 0:
        raise argparse.ArgumentTypeError("debe ser mayor o igual a 0")

    return parsed


def positive_integer(value):
    parsed = int(value)

    if parsed < 1:
        raise argparse.ArgumentTypeError("debe ser mayor o igual a 1")

    return parsed


def build_parser():
    parser = argparse.ArgumentParser(
        description="Verifica degradacion controlada durante una caida de MySQL.",
    )
    parser.add_argument("--liveness-url", required=True)
    parser.add_argument("--readiness-url", required=True)
    parser.add_argument("--budget", type=positive_float, default=20)
    parser.add_argument("--interval", type=non_negative_float, default=1)
    parser.add_argument("--timeout", type=positive_integer, default=5)
    parser.add_argument("--consecutive", type=positive_integer, default=2)
    parser.add_argument("--output", default="")
    parser.add_argument("--allow-http", action="store_true")
    return parser


def main():
    arguments = build_parser().parse_args()

    try:
        exit_code, report = verify_database_outage(
            liveness_url=arguments.liveness_url,
            readiness_url=arguments.readiness_url,
            budget=arguments.budget,
            interval=arguments.interval,
            timeout=arguments.timeout,
            consecutive=arguments.consecutive,
            allow_http=arguments.allow_http,
        )
    except (MonitorError, ValueError) as exc:
        report = {
            "event": "database_outage",
            "status": "configuration_error",
            "error": str(exc),
        }
        exit_code = 2

    write_report(arguments.output, report)
    print(
        json.dumps(report, ensure_ascii=False, separators=(",", ":")),
        file=sys.stdout if exit_code == 0 else sys.stderr,
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
