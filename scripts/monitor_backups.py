#!/usr/bin/env python3
"""
Verifica antiguedad, integridad y capacidad del almacenamiento de backups.
Usa solo la biblioteca estandar para ejecutarse desde Compose, cron o CI.
"""

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


BACKUP_ID_PATTERN = re.compile(r"^[0-9]{8}T[0-9]{6}Z$")
MANIFEST_PATTERN = re.compile(
    r"^(?P<digest>[0-9a-f]{64})  (?P<name>[A-Za-z0-9._-]+)$"
)
PAYLOAD_FILES = ("database.sql.gz", "media.tar.gz", "metadata.txt")
REQUIRED_FILES = (*PAYLOAD_FILES, "manifest.sha256")
MAX_WEBHOOK_RESPONSE_BYTES = 64 * 1024


class BackupMonitorError(RuntimeError):
    """Error esperado al validar el estado de los respaldos."""


class NoRedirectHandler(HTTPRedirectHandler):
    """Evita reenviar el token del webhook durante una redireccion."""

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


HTTP_OPENER = build_opener(NoRedirectHandler())


def utc_now():
    return datetime.now(timezone.utc)


def parse_backup_id(value):
    if not BACKUP_ID_PATTERN.fullmatch(value):
        raise BackupMonitorError(
            "latest.txt no contiene un identificador UTC valido."
        )

    return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(
        tzinfo=timezone.utc
    )


def parse_metadata(path):
    values = {}

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in raw_line:
            raise BackupMonitorError("metadata.txt contiene una linea invalida.")

        key, value = raw_line.split("=", 1)

        if not key or key in values:
            raise BackupMonitorError(
                "metadata.txt contiene claves vacias o duplicadas."
            )

        values[key] = value

    required_keys = {"backup_id", "created_at_utc", "database", "mysql_host"}
    missing = sorted(required_keys.difference(values))

    if missing:
        raise BackupMonitorError(
            f"metadata.txt no contiene: {', '.join(missing)}."
        )

    try:
        created_at = datetime.strptime(
            values["created_at_utc"],
            "%Y-%m-%dT%H:%M:%SZ",
        ).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise BackupMonitorError(
            "metadata.txt contiene created_at_utc invalido."
        ) from exc

    return values, created_at


def regular_file(path, label):
    if path.is_symlink() or not path.is_file():
        raise BackupMonitorError(f"{label} debe ser un archivo regular.")

    return path


def read_manifest(path):
    entries = {}

    for raw_line in path.read_text(encoding="ascii").splitlines():
        match = MANIFEST_PATTERN.fullmatch(raw_line)

        if not match:
            raise BackupMonitorError(
                "manifest.sha256 contiene una linea invalida."
            )

        name = match.group("name")

        if name in entries:
            raise BackupMonitorError(
                "manifest.sha256 contiene archivos duplicados."
            )

        entries[name] = match.group("digest")

    if set(entries) != set(PAYLOAD_FILES):
        raise BackupMonitorError(
            "manifest.sha256 no contiene exactamente los archivos esperados."
        )

    return entries


def sha256_file(path):
    digest = hashlib.sha256()

    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)

    return digest.hexdigest()


def validate_database_archive(path, minimum_bytes):
    uncompressed_bytes = 0

    try:
        with gzip.open(path, "rb") as source:
            while chunk := source.read(1024 * 1024):
                uncompressed_bytes += len(chunk)
    except (OSError, EOFError) as exc:
        raise BackupMonitorError(
            "database.sql.gz esta corrupto o incompleto."
        ) from exc

    if uncompressed_bytes < minimum_bytes:
        raise BackupMonitorError(
            "database.sql.gz es menor que BACKUP_MIN_DATABASE_BYTES."
        )

    return uncompressed_bytes


def validate_media_archive(path):
    members = 0

    try:
        with tarfile.open(path, mode="r:gz") as archive:
            for member in archive:
                member_path = PurePosixPath(member.name)

                if member_path.is_absolute() or ".." in member_path.parts:
                    raise BackupMonitorError(
                        "media.tar.gz contiene una ruta insegura."
                    )

                if member.issym() or member.islnk():
                    raise BackupMonitorError(
                        "media.tar.gz contiene enlaces no permitidos."
                    )

                members += 1
    except (tarfile.TarError, OSError, EOFError) as exc:
        raise BackupMonitorError(
            "media.tar.gz esta corrupto o incompleto."
        ) from exc

    if members < 1:
        raise BackupMonitorError("media.tar.gz no contiene entradas.")

    return members


def verify_backup(
    backup_root,
    max_age_hours=26,
    future_tolerance_minutes=5,
    min_database_bytes=128,
    min_media_bytes=32,
    min_free_bytes=1024 * 1024 * 1024,
    min_free_percent=10,
    min_free_copies=2,
    now=utc_now,
    disk_usage=shutil.disk_usage,
):
    if max_age_hours <= 0:
        raise BackupMonitorError("max_age_hours debe ser mayor que 0.")

    if future_tolerance_minutes < 0:
        raise BackupMonitorError(
            "future_tolerance_minutes debe ser mayor o igual a 0."
        )

    for value, label in (
        (min_database_bytes, "min_database_bytes"),
        (min_media_bytes, "min_media_bytes"),
        (min_free_bytes, "min_free_bytes"),
        (min_free_copies, "min_free_copies"),
    ):
        if value < 0:
            raise BackupMonitorError(f"{label} debe ser mayor o igual a 0.")

    if not 0 <= min_free_percent <= 100:
        raise BackupMonitorError(
            "min_free_percent debe estar entre 0 y 100."
        )

    root = Path(os.path.abspath(os.fspath(backup_root)))

    if root.is_symlink() or root.parent.is_symlink():
        raise BackupMonitorError(
            "BACKUP_ROOT no puede ser un enlace simbolico."
        )

    if not root.is_dir():
        raise BackupMonitorError("BACKUP_ROOT no existe o no es un directorio.")

    latest_path = regular_file(root / "latest.txt", "latest.txt")
    backup_id = latest_path.read_text(encoding="ascii").strip()
    backup_id_time = parse_backup_id(backup_id)
    backup_directory = root / backup_id

    if backup_directory.is_symlink() or not backup_directory.is_dir():
        raise BackupMonitorError(
            "El directorio del ultimo backup no es un directorio regular."
        )

    files = {
        name: regular_file(backup_directory / name, name)
        for name in REQUIRED_FILES
    }
    manifest = read_manifest(files["manifest.sha256"])

    for name, expected_digest in manifest.items():
        if sha256_file(files[name]) != expected_digest:
            raise BackupMonitorError(f"Checksum invalido para {name}.")

    metadata, created_at = parse_metadata(files["metadata.txt"])

    if metadata["backup_id"] != backup_id:
        raise BackupMonitorError(
            "metadata.txt no coincide con el identificador del backup."
        )

    if abs((created_at - backup_id_time).total_seconds()) > 5:
        raise BackupMonitorError(
            "created_at_utc no coincide con el identificador del backup."
        )

    current_time = now()

    if current_time.tzinfo is None:
        raise BackupMonitorError("now debe devolver una fecha con zona horaria.")

    age_seconds = (current_time - created_at).total_seconds()

    if age_seconds < -(future_tolerance_minutes * 60):
        raise BackupMonitorError("El backup tiene una fecha futura invalida.")

    age_hours = max(age_seconds, 0) / 3600

    if age_hours > max_age_hours:
        raise BackupMonitorError(
            f"El ultimo backup tiene {age_hours:.2f} horas de antiguedad."
        )

    database_bytes = validate_database_archive(
        files["database.sql.gz"],
        min_database_bytes,
    )

    if files["media.tar.gz"].stat().st_size < min_media_bytes:
        raise BackupMonitorError(
            "media.tar.gz es menor que BACKUP_MIN_MEDIA_BYTES."
        )

    media_members = validate_media_archive(files["media.tar.gz"])
    backup_bytes = sum(path.stat().st_size for path in files.values())
    usage = disk_usage(root)
    free_percent = (usage.free / usage.total * 100) if usage.total else 0
    required_free_bytes = max(
        min_free_bytes,
        backup_bytes * min_free_copies,
    )

    if usage.free < required_free_bytes:
        raise BackupMonitorError(
            "El almacenamiento no tiene espacio para la reserva configurada."
        )

    if free_percent < min_free_percent:
        raise BackupMonitorError(
            f"El espacio libre es {free_percent:.2f} %, menor al minimo."
        )

    return {
        "event": "backup_health",
        "status": "ok",
        "backup_id": backup_id,
        "created_at_utc": created_at.isoformat().replace("+00:00", "Z"),
        "age_hours": round(age_hours, 3),
        "backup_bytes": backup_bytes,
        "database_uncompressed_bytes": database_bytes,
        "media_members": media_members,
        "disk_free_bytes": usage.free,
        "disk_free_percent": round(free_percent, 3),
        "required_free_bytes": required_free_bytes,
    }


def validate_webhook_url(value):
    from urllib.parse import urlsplit

    parsed = urlsplit(value)

    if parsed.scheme != "https" or not parsed.hostname:
        raise BackupMonitorError("MONITOR_WEBHOOK_URL debe usar HTTPS.")

    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise BackupMonitorError(
            "MONITOR_WEBHOOK_URL no debe incluir credenciales, query o fragmento."
        )

    return value


def send_webhook(url, token, event, timeout):
    summary = (
        f"[CRITICAL] Backup de Vape Shop no saludable: {event['error']}"
    )
    payload = json.dumps(
        {"text": summary, "content": summary, "event": event},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "vapes-shop-backup-monitor/1.0",
    }

    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = Request(url, data=payload, headers=headers, method="POST")

    try:
        with HTTP_OPENER.open(request, timeout=timeout) as response:
            body = response.read(MAX_WEBHOOK_RESPONSE_BYTES + 1)

            if len(body) > MAX_WEBHOOK_RESPONSE_BYTES:
                raise BackupMonitorError(
                    "La respuesta del webhook supera el limite permitido."
                )
    except HTTPError as exc:
        raise BackupMonitorError(
            f"El webhook respondio HTTP {exc.code}."
        ) from exc
    except (TimeoutError, URLError, OSError) as exc:
        raise BackupMonitorError(
            f"No fue posible enviar el webhook: {exc.__class__.__name__}."
        ) from exc


def run_monitor(**kwargs):
    webhook_url = kwargs.pop("webhook_url", "")
    webhook_token = kwargs.pop("webhook_token", "")
    webhook_timeout = kwargs.pop("webhook_timeout", 10)

    try:
        return 0, verify_backup(**kwargs)
    except (BackupMonitorError, OSError, UnicodeError, ValueError) as exc:
        event = {
            "event": "backup_health",
            "status": "critical",
            "error": str(exc),
        }

        if webhook_url:
            try:
                send_webhook(
                    validate_webhook_url(webhook_url),
                    webhook_token,
                    event,
                    webhook_timeout,
                )
                event["alert"] = "sent"
            except BackupMonitorError as webhook_error:
                event["alert"] = "failed"
                event["alert_error"] = str(webhook_error)
        else:
            event["alert"] = "not_configured"

        return 1, event


def non_negative_integer(value):
    parsed = int(value)

    if parsed < 0:
        raise argparse.ArgumentTypeError("debe ser mayor o igual a 0")

    return parsed


def positive_float(value):
    parsed = float(value)

    if parsed <= 0:
        raise argparse.ArgumentTypeError("debe ser mayor que 0")

    return parsed


def percentage(value):
    parsed = float(value)

    if not 0 <= parsed <= 100:
        raise argparse.ArgumentTypeError("debe estar entre 0 y 100")

    return parsed


def build_parser():
    parser = argparse.ArgumentParser(
        description="Verifica salud e integridad del ultimo backup.",
    )
    parser.add_argument(
        "--root",
        default=os.environ.get("BACKUP_ROOT", "./backups"),
    )
    parser.add_argument(
        "--max-age-hours",
        type=positive_float,
        default=float(os.environ.get("BACKUP_MAX_AGE_HOURS", "26")),
    )
    parser.add_argument(
        "--future-tolerance-minutes",
        type=non_negative_integer,
        default=int(os.environ.get("BACKUP_FUTURE_TOLERANCE_MINUTES", "5")),
    )
    parser.add_argument(
        "--min-database-bytes",
        type=non_negative_integer,
        default=int(os.environ.get("BACKUP_MIN_DATABASE_BYTES", "128")),
    )
    parser.add_argument(
        "--min-media-bytes",
        type=non_negative_integer,
        default=int(os.environ.get("BACKUP_MIN_MEDIA_BYTES", "32")),
    )
    parser.add_argument(
        "--min-free-bytes",
        type=non_negative_integer,
        default=int(os.environ.get("BACKUP_MIN_FREE_BYTES", "1073741824")),
    )
    parser.add_argument(
        "--min-free-percent",
        type=percentage,
        default=float(os.environ.get("BACKUP_MIN_FREE_PERCENT", "10")),
    )
    parser.add_argument(
        "--min-free-copies",
        type=non_negative_integer,
        default=int(os.environ.get("BACKUP_MIN_FREE_COPIES", "2")),
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
        "--webhook-timeout",
        type=positive_float,
        default=10,
    )
    parser.add_argument("--output", default="")
    return parser


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
        raise BackupMonitorError(
            "El reporte de monitoreo de backups no admite enlaces simbolicos."
        )

    temporary_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary_path, 0o600)
    os.replace(temporary_path, output_path)


def main():
    arguments = build_parser().parse_args()
    exit_code, event = run_monitor(
        backup_root=arguments.root,
        max_age_hours=arguments.max_age_hours,
        future_tolerance_minutes=arguments.future_tolerance_minutes,
        min_database_bytes=arguments.min_database_bytes,
        min_media_bytes=arguments.min_media_bytes,
        min_free_bytes=arguments.min_free_bytes,
        min_free_percent=arguments.min_free_percent,
        min_free_copies=arguments.min_free_copies,
        webhook_url=arguments.webhook_url,
        webhook_token=arguments.webhook_token,
        webhook_timeout=arguments.webhook_timeout,
    )

    write_report(arguments.output, event)

    print(
        json.dumps(event, ensure_ascii=False, separators=(",", ":")),
        file=sys.stdout if exit_code == 0 else sys.stderr,
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
