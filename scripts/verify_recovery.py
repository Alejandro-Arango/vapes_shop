#!/usr/bin/env python3
"""
Mide cuanto tarda readiness en recuperar estabilidad despues de una falla.
Exige varias respuestas saludables consecutivas para evitar falsos positivos.
"""

import argparse
import json
import sys
import time
from pathlib import Path

SCRIPT_DIRECTORY = Path(__file__).resolve().parent

if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

from monitor_production import MonitorError, check_readiness, validate_url


def write_report(path, report):
    if not path:
        return

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def verify_recovery(
    target_url,
    budget=30,
    interval=1,
    timeout=3,
    consecutive=3,
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

    target_url = validate_url(
        target_url,
        "RECOVERY_HEALTH_URL",
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
            result = check_readiness(target_url, timeout)
            consecutive_successes += 1
            request_ids.append(result["request_id"])

            if consecutive_successes >= consecutive:
                elapsed = monotonic() - started_at
                return 0, {
                    "event": "readiness_recovery",
                    "status": "recovered",
                    "target": target_url,
                    "elapsed_seconds": round(elapsed, 3),
                    "attempts": attempts,
                    "consecutive_successes": consecutive_successes,
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
        "event": "readiness_recovery",
        "status": "timeout",
        "target": target_url,
        "elapsed_seconds": round(elapsed, 3),
        "attempts": attempts,
        "consecutive_successes": consecutive_successes,
        "errors": errors,
    }


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
        description="Verifica recuperacion estable de readiness.",
    )
    parser.add_argument("--url", required=True)
    parser.add_argument("--budget", type=positive_float, default=30)
    parser.add_argument("--interval", type=non_negative_float, default=1)
    parser.add_argument("--timeout", type=positive_integer, default=3)
    parser.add_argument("--consecutive", type=positive_integer, default=3)
    parser.add_argument("--output", default="")
    parser.add_argument("--allow-http", action="store_true")
    return parser


def main():
    arguments = build_parser().parse_args()

    try:
        exit_code, report = verify_recovery(
            target_url=arguments.url,
            budget=arguments.budget,
            interval=arguments.interval,
            timeout=arguments.timeout,
            consecutive=arguments.consecutive,
            allow_http=arguments.allow_http,
        )
    except (MonitorError, ValueError) as exc:
        report = {
            "event": "readiness_recovery",
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
