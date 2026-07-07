#!/usr/bin/env python3
"""
Ejecuta un smoke externo contra la cara publica del sitio.
Valida home, liveness, readiness y cabeceras de seguridad del proxy.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4


MAX_RESPONSE_BYTES = 256 * 1024
USER_AGENT = "vapes-shop-public-smoke/1.0"


class SmokeError(RuntimeError):
    """Error esperado durante un smoke operativo."""


class NoRedirectHandler(HTTPRedirectHandler):
    """Evita seguir redirecciones y ocultar problemas del proxy publico."""

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


def validate_base_url(value, label, allow_http=False):
    parsed = urlsplit(value)
    allowed_schemes = {"https"}

    if allow_http:
        allowed_schemes.add("http")

    if parsed.scheme not in allowed_schemes:
        raise SmokeError(f"{label} debe usar HTTPS.")

    if not parsed.hostname:
        raise SmokeError(f"{label} debe incluir un host valido.")

    if parsed.username or parsed.password:
        raise SmokeError(f"{label} no debe incluir credenciales.")

    if parsed.query or parsed.fragment:
        raise SmokeError(f"{label} no debe incluir query string ni fragmento.")

    if parsed.path not in ("", "/"):
        raise SmokeError(f"{label} debe apuntar a la raiz del sitio.")

    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def safe_url(value):
    parsed = urlsplit(value)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def build_url(base_url, path):
    parsed = urlsplit(base_url)
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def read_limited(response):
    body = response.read(MAX_RESPONSE_BYTES + 1)

    if len(body) > MAX_RESPONSE_BYTES:
        raise SmokeError("La respuesta supera el limite permitido.")

    return body


def fetch(target_url, accept, timeout):
    smoke_request_id = f"smoke-{uuid4().hex}"
    request = Request(
        target_url,
        headers={
            "Accept": accept,
            "User-Agent": USER_AGENT,
            "X-Request-ID": smoke_request_id,
        },
        method="GET",
    )

    try:
        with HTTP_OPENER.open(request, timeout=timeout) as response:
            body = read_limited(response)
            return {
                "url": safe_url(target_url),
                "status_code": response.status,
                "content_type": response.headers.get("Content-Type", ""),
                "headers": response.headers,
                "body": body,
                "request_id": response.headers.get(
                    "X-Request-ID",
                    smoke_request_id,
                ),
            }
    except HTTPError as exc:
        request_id = exc.headers.get("X-Request-ID", smoke_request_id)
        raise SmokeError(
            f"{safe_url(target_url)} respondio HTTP {exc.code}; "
            f"request_id={request_id}."
        ) from exc
    except (TimeoutError, URLError, OSError) as exc:
        raise SmokeError(
            f"No fue posible conectar con {safe_url(target_url)}: "
            f"{exc.__class__.__name__}."
        ) from exc


def require_header(headers, name):
    value = headers.get(name, "").strip()

    if not value:
        raise SmokeError(f"Falta la cabecera {name}.")

    return value


def require_header_value(headers, name, expected):
    value = require_header(headers, name)

    if value.lower() != expected.lower():
        raise SmokeError(
            f"{name} debe ser {expected}; valor actual: {value}."
        )

    return value


def require_header_contains(headers, name, fragments):
    value = require_header(headers, name)
    normalized_value = value.lower()
    missing = [
        fragment
        for fragment in fragments
        if fragment.lower() not in normalized_value
    ]

    if missing:
        raise SmokeError(
            f"{name} no contiene los fragmentos requeridos: "
            f"{', '.join(missing)}."
        )

    return value


def validate_liveness(base_url, timeout):
    response = fetch(build_url(base_url, "/livez"), "text/plain", timeout)

    if response["status_code"] != 200:
        raise SmokeError("/livez debe responder HTTP 200.")

    if "text/plain" not in response["content_type"].lower():
        raise SmokeError("/livez debe responder Content-Type text/plain.")

    if response["body"].decode("utf-8", errors="replace").strip() != "ok":
        raise SmokeError("/livez debe responder cuerpo ok.")

    require_header(response["headers"], "X-Request-ID")
    require_header_contains(response["headers"], "Cache-Control", ("no-store",))

    return {
        "target": response["url"],
        "request_id": response["request_id"],
    }


def validate_readiness(base_url, timeout):
    response = fetch(
        build_url(base_url, "/healthz"),
        "application/json",
        timeout,
    )

    if response["status_code"] != 200:
        raise SmokeError("/healthz debe responder HTTP 200.")

    if "application/json" not in response["content_type"].lower():
        raise SmokeError("/healthz debe responder Content-Type JSON.")

    try:
        payload = json.loads(response["body"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SmokeError("/healthz debe responder JSON valido.") from exc

    expected_values = {
        "status": "ok",
        "database": "available",
        "cache": "available",
    }
    invalid_fields = [
        field
        for field, expected in expected_values.items()
        if payload.get(field) != expected
    ]

    if invalid_fields:
        raise SmokeError(
            "/healthz reporto campos no saludables: "
            f"{', '.join(invalid_fields)}."
        )

    require_header(response["headers"], "X-Request-ID")
    require_header_contains(response["headers"], "Cache-Control", ("no-store",))

    return {
        "target": response["url"],
        "request_id": response["request_id"],
        "details": payload,
    }


def validate_public_headers(headers, require_hsts):
    require_header_value(headers, "X-Content-Type-Options", "nosniff")
    require_header_value(headers, "X-Frame-Options", "DENY")
    require_header_value(
        headers,
        "Cross-Origin-Opener-Policy",
        "same-origin",
    )
    require_header_value(
        headers,
        "Cross-Origin-Resource-Policy",
        "same-origin",
    )
    require_header_contains(
        headers,
        "Content-Security-Policy",
        (
            "default-src 'self'",
            "object-src 'none'",
            "frame-ancestors 'none'",
            "script-src 'self'",
            "connect-src 'self'",
        ),
    )
    require_header_contains(
        headers,
        "Permissions-Policy",
        ("camera=()", "microphone=()", "geolocation=()"),
    )

    referrer_policy = require_header(headers, "Referrer-Policy")
    if referrer_policy.lower() == "unsafe-url":
        raise SmokeError("Referrer-Policy no debe ser unsafe-url.")

    if require_hsts:
        hsts = require_header(headers, "Strict-Transport-Security")
        require_header_contains(
            headers,
            "Strict-Transport-Security",
            ("max-age=",),
        )
        if "max-age=0" in hsts.replace(" ", "").lower():
            raise SmokeError("Strict-Transport-Security no debe usar max-age=0.")


def validate_home(base_url, timeout, require_hsts):
    response = fetch(build_url(base_url, "/"), "text/html", timeout)

    if response["status_code"] != 200:
        raise SmokeError("La home debe responder HTTP 200.")

    if "text/html" not in response["content_type"].lower():
        raise SmokeError("La home debe responder Content-Type HTML.")

    html = response["body"].decode("utf-8", errors="replace")
    required_fragments = ("Vape Shop", "contact-form", "product-list")
    missing = [
        fragment
        for fragment in required_fragments
        if fragment not in html
    ]

    if missing:
        raise SmokeError(
            "La home no contiene marcadores funcionales esperados: "
            f"{', '.join(missing)}."
        )

    require_header(response["headers"], "X-Request-ID")
    validate_public_headers(response["headers"], require_hsts=require_hsts)

    return {
        "target": response["url"],
        "request_id": response["request_id"],
        "bytes": len(response["body"]),
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
        or temporary_path.exists()
        or temporary_path.is_symlink()
    ):
        raise SmokeError(
            "El reporte de smoke publico no admite enlaces simbolicos "
            "ni temporales preexistentes."
        )

    temporary_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary_path, 0o600)
    os.replace(temporary_path, output_path)


def run_smoke(
    base_url,
    timeout=10,
    allow_http=False,
    require_hsts=None,
):
    if timeout < 1:
        raise SmokeError("timeout debe ser mayor o igual a 1.")

    base_url = validate_base_url(
        base_url,
        "PUBLIC_SITE_URL",
        allow_http=allow_http,
    )
    parsed = urlsplit(base_url)

    if require_hsts is None:
        require_hsts = parsed.scheme == "https"

    checks = []

    for name, checker in (
        ("liveness", lambda: validate_liveness(base_url, timeout)),
        ("readiness", lambda: validate_readiness(base_url, timeout)),
        ("home", lambda: validate_home(base_url, timeout, require_hsts)),
    ):
        try:
            detail = checker()
            checks.append(
                {
                    "name": name,
                    "status": "ok",
                    **detail,
                }
            )
        except SmokeError as exc:
            checks.append(
                {
                    "name": name,
                    "status": "critical",
                    "error": str(exc),
                }
            )

    failed_checks = [
        check
        for check in checks
        if check["status"] != "ok"
    ]
    status = "critical" if failed_checks else "ok"
    report = {
        "event": "public_site_smoke",
        "status": status,
        "checked_at": utc_now(),
        "target": safe_url(base_url),
        "checks": checks,
    }

    if failed_checks:
        report["error"] = failed_checks[0]["error"]

    return (1 if failed_checks else 0), report


def positive_integer(value):
    parsed = int(value)

    if parsed < 1:
        raise argparse.ArgumentTypeError("debe ser mayor o igual a 1")

    return parsed


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Valida la cara publica del sitio despues de desplegar."
        ),
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("PUBLIC_SITE_URL", ""),
        help="URL base HTTPS del sitio, por ejemplo https://tienda.example.",
    )
    parser.add_argument(
        "--timeout",
        type=positive_integer,
        default=10,
    )
    parser.add_argument(
        "--output",
        default=os.environ.get("PUBLIC_SMOKE_REPORT_PATH", ""),
        help="Ruta opcional para guardar el reporte JSON del smoke.",
    )
    parser.add_argument(
        "--allow-http",
        action="store_true",
        help="Permite HTTP solo para pruebas locales contra el proxy.",
    )
    parser.add_argument(
        "--skip-hsts",
        action="store_true",
        help="Omite HSTS solo en staging transitorio sin TLS final.",
    )
    return parser


def main():
    parser = build_parser()
    arguments = parser.parse_args()

    if not arguments.url:
        parser.error("define --url o la variable PUBLIC_SITE_URL")

    try:
        exit_code, report = run_smoke(
            base_url=arguments.url,
            timeout=arguments.timeout,
            allow_http=arguments.allow_http,
            require_hsts=False if arguments.skip_hsts else None,
        )
    except (SmokeError, ValueError) as exc:
        report = {
            "event": "public_site_smoke",
            "status": "configuration_error",
            "checked_at": utc_now(),
            "error": str(exc),
        }
        exit_code = 2

    try:
        write_report(arguments.output, report)
    except (SmokeError, ValueError) as exc:
        report["report_error"] = str(exc)
        if exit_code == 0:
            exit_code = 2

    output = json.dumps(
        report,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    print(output, file=sys.stdout if exit_code == 0 else sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
