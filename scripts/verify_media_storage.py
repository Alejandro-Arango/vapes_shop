#!/usr/bin/env python3
"""
Verifica lectura persistente y capacidad de escritura del almacenamiento media.
La ejecucion requiere una habilitacion explicita para evitar sondas accidentales.
"""

import argparse
import json
import os
import sys
from pathlib import Path, PurePosixPath
from uuid import uuid4


PROBE_PAYLOAD = b"vapes-shop-media-storage-probe\n"


def ensure_enabled():
    if os.environ.get("MEDIA_STORAGE_TEST_ENABLED", "").lower() != "true":
        raise RuntimeError(
            "Define MEDIA_STORAGE_TEST_ENABLED=true para ejecutar la sonda."
        )


def validate_relative_name(value, label):
    path = PurePosixPath(value)

    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in value
    ):
        raise RuntimeError(f"{label} debe ser una ruta relativa segura.")

    return path.as_posix()


def read_bytes(storage, name):
    with storage.open(name, "rb") as stored_file:
        return stored_file.read()


def probe_storage(
    storage,
    content_factory,
    expected,
    marker_name,
    marker_value,
    token=None,
):
    if expected not in {"available", "unavailable"}:
        raise RuntimeError("expected debe ser available o unavailable.")

    marker_name = validate_relative_name(marker_name, "marker_name")
    marker_content = read_bytes(storage, marker_name)
    expected_marker = marker_value.encode("utf-8")

    if marker_content != expected_marker:
        raise RuntimeError("El archivo persistente no conserva su contenido.")

    token = token or uuid4().hex
    probe_name = validate_relative_name(
        f"operational/.write-probe-{token}.bin",
        "probe_name",
    )
    saved_name = ""
    write_error = ""

    try:
        saved_name = storage.save(
            probe_name,
            content_factory(PROBE_PAYLOAD, name=Path(probe_name).name),
        )

        if read_bytes(storage, saved_name) != PROBE_PAYLOAD:
            raise RuntimeError("La sonda escrita no pudo leerse sin cambios.")
    except OSError as exc:
        write_error = exc.__class__.__name__
    finally:
        if saved_name and storage.exists(saved_name):
            storage.delete(saved_name)

    if expected == "available" and write_error:
        raise RuntimeError(
            f"El almacenamiento debia aceptar escritura: {write_error}."
        )

    if expected == "unavailable" and not write_error:
        raise RuntimeError(
            "El almacenamiento debia rechazar escritura y la acepto."
        )

    return {
        "event": "media_storage",
        "status": (
            "available"
            if expected == "available"
            else "unavailable_as_expected"
        ),
        "expected": expected,
        "marker_name": marker_name,
        "marker_bytes": len(marker_content),
        "probe_name": probe_name,
        "write_error": write_error,
    }


def configure_django():
    project_root = Path(
        os.environ.get(
            "DJANGO_PROJECT_ROOT",
            Path(__file__).resolve().parents[1] / "backend",
        )
    ).resolve()
    sys.path.insert(0, str(project_root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mi_tienda.settings")

    import django

    django.setup()


def write_report(path, report):
    output_path = Path(os.path.abspath(os.fspath(path)))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(f"{output_path.suffix}.tmp")

    if (
        output_path.is_symlink()
        or output_path.parent.is_symlink()
        or temporary_path.exists()
        or temporary_path.is_symlink()
    ):
        raise RuntimeError(
            "El reporte de almacenamiento media no admite enlaces simbolicos "
            "ni temporales preexistentes."
        )

    temporary_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary_path, 0o600)
    os.replace(temporary_path, output_path)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Verifica disponibilidad del almacenamiento media.",
    )
    parser.add_argument(
        "--expect",
        choices=("available", "unavailable"),
        required=True,
    )
    parser.add_argument(
        "--marker-name",
        default="operational/persistent.txt",
    )
    parser.add_argument(
        "--marker-value",
        default="persistent-media\n",
    )
    parser.add_argument("--output", required=True)
    return parser


def main():
    arguments = build_parser().parse_args()
    ensure_enabled()
    configure_django()

    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage

    report = probe_storage(
        default_storage,
        ContentFile,
        arguments.expect,
        arguments.marker_name,
        arguments.marker_value,
    )
    write_report(arguments.output, report)
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
