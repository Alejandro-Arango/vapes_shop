#!/usr/bin/env python3
"""Genera y valida el manifiesto inmutable de una release recuperable."""

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

SCRIPT_DIRECTORY = Path(__file__).resolve().parent

if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

from deploy_production import (
    DeploymentError,
    validate_image_reference,
)


SCHEMA = "vapes-shop/recovery-manifest/v1"
REPOSITORY_PATTERN = re.compile(
    r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"
)
RELEASE_TAG_PATTERN = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
CHECKSUM_PATTERN = re.compile(
    r"^(?P<digest>[0-9a-f]{64})  recovery-manifest\.json$"
)


class ReleaseManifestError(RuntimeError):
    """El manifiesto no cumple el contrato de recuperación."""


def sha256_file(path):
    digest = hashlib.sha256()

    with Path(path).open("rb") as manifest_file:
        for chunk in iter(lambda: manifest_file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def required_regular_file(path, label):
    candidate = Path(path)

    if candidate.is_symlink() or not candidate.is_file():
        raise ReleaseManifestError(
            f"{label} debe ser un archivo regular."
        )

    return candidate


def validate_repository(value):
    repository = value.strip()

    if not REPOSITORY_PATTERN.fullmatch(repository):
        raise ReleaseManifestError(
            "repository debe usar formato propietario/repositorio."
        )

    return repository.lower()


def validate_release_tag(value):
    tag = value.strip()

    if not RELEASE_TAG_PATTERN.fullmatch(tag):
        raise ReleaseManifestError(
            "release_tag debe usar formato vMAJOR.MINOR.PATCH."
        )

    return tag


def validate_commit(value):
    commit = value.strip().lower()

    if not COMMIT_PATTERN.fullmatch(commit):
        raise ReleaseManifestError(
            "source_commit debe contener 40 caracteres hexadecimales."
        )

    return commit


def validate_positive_seconds(value):
    try:
        seconds = float(value)
    except (TypeError, ValueError) as exc:
        raise ReleaseManifestError(
            "recovery.rto_seconds debe ser numerico."
        ) from exc

    if seconds <= 0:
        raise ReleaseManifestError(
            "recovery.rto_seconds debe ser mayor que cero."
        )

    return seconds


def expected_image_prefix(repository, suffix=""):
    return f"ghcr.io/{repository.lower()}{suffix}@sha256:"


def validate_manifest(payload, expected_repository="", expected_tag=""):
    if not isinstance(payload, dict):
        raise ReleaseManifestError("El manifiesto debe ser un objeto JSON.")

    if payload.get("schema") != SCHEMA:
        raise ReleaseManifestError("schema de manifiesto no soportado.")

    repository = validate_repository(payload.get("repository", ""))
    release_tag = validate_release_tag(payload.get("release_tag", ""))
    source_commit = validate_commit(payload.get("source_commit", ""))

    if expected_repository and (
        repository.lower() != validate_repository(expected_repository).lower()
    ):
        raise ReleaseManifestError(
            "El manifiesto no pertenece al repositorio esperado."
        )

    if expected_tag and release_tag != validate_release_tag(expected_tag):
        raise ReleaseManifestError(
            "El manifiesto no corresponde a la release esperada."
        )

    images = payload.get("images")

    if not isinstance(images, dict):
        raise ReleaseManifestError("images debe ser un objeto.")

    try:
        app_image = validate_image_reference(
            images.get("application", ""),
            "images.application",
        )
        backup_image = validate_image_reference(
            images.get("operations", ""),
            "images.operations",
        )
    except DeploymentError as exc:
        raise ReleaseManifestError(str(exc)) from exc

    if not app_image.lower().startswith(
        expected_image_prefix(repository)
    ):
        raise ReleaseManifestError(
            "images.application no pertenece al repositorio esperado."
        )

    if not backup_image.lower().startswith(
        expected_image_prefix(repository, "-backup")
    ):
        raise ReleaseManifestError(
            "images.operations no pertenece al repositorio esperado."
        )

    recovery = payload.get("recovery")

    if not isinstance(recovery, dict):
        raise ReleaseManifestError("recovery debe ser un objeto.")

    rto_seconds = validate_positive_seconds(
        recovery.get("rto_seconds")
    )
    return {
        "schema": SCHEMA,
        "repository": repository,
        "release_tag": release_tag,
        "source_commit": source_commit,
        "images": {
            "application": app_image,
            "operations": backup_image,
        },
        "recovery": {
            "rto_seconds": rto_seconds,
        },
    }


def build_manifest(
    repository,
    release_tag,
    source_commit,
    app_image,
    backup_image,
    rto_seconds,
):
    return validate_manifest(
        {
            "schema": SCHEMA,
            "repository": repository,
            "release_tag": release_tag,
            "source_commit": source_commit,
            "images": {
                "application": app_image,
                "operations": backup_image,
            },
            "recovery": {
                "rto_seconds": rto_seconds,
            },
        },
        expected_repository=repository,
        expected_tag=release_tag,
    )


def write_manifest(output_path, payload):
    path = Path(os.path.abspath(os.fspath(output_path)))

    if path.name != "recovery-manifest.json":
        raise ReleaseManifestError(
            "El asset debe llamarse recovery-manifest.json."
        )

    if path.is_symlink() or path.parent.is_symlink():
        raise ReleaseManifestError(
            "El manifiesto no puede reemplazar un enlace simbolico."
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")

    if temporary_path.is_symlink():
        raise ReleaseManifestError(
            "El manifiesto no puede escribir sobre un temporal simbolico."
        )

    temporary_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary_path, 0o600)
    os.replace(temporary_path, path)


def write_checksum(checksum_path, manifest_path):
    path = Path(os.path.abspath(os.fspath(checksum_path)))
    manifest = Path(
        os.path.abspath(
            os.fspath(
                required_regular_file(
                    manifest_path,
                    "recovery-manifest.json",
                )
            )
        )
    )

    if path.is_symlink() or path.parent.is_symlink():
        raise ReleaseManifestError(
            "El checksum no puede reemplazar un enlace simbolico."
        )

    if path == manifest:
        raise ReleaseManifestError(
            "El checksum no puede sobrescribir el manifiesto."
        )

    if path.name != "recovery-manifest.sha256":
        raise ReleaseManifestError(
            "El asset debe llamarse recovery-manifest.sha256."
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")

    if temporary_path.is_symlink():
        raise ReleaseManifestError(
            "El checksum no puede escribir sobre un temporal simbolico."
        )

    temporary_path.write_text(
        f"{sha256_file(manifest)}  recovery-manifest.json\n",
        encoding="ascii",
    )
    os.chmod(temporary_path, 0o600)
    os.replace(temporary_path, path)


def verify_checksum(manifest_path, checksum_path):
    manifest_file = required_regular_file(
        manifest_path,
        "recovery-manifest.json",
    )
    checksum_file = required_regular_file(
        checksum_path,
        "recovery-manifest.sha256",
    )

    try:
        checksum_text = checksum_file.read_text(
            encoding="ascii"
        ).strip()
    except OSError as exc:
        raise ReleaseManifestError(
            f"No fue posible leer el checksum: {exc.__class__.__name__}."
        ) from exc

    match = CHECKSUM_PATTERN.fullmatch(checksum_text)

    if not match:
        raise ReleaseManifestError(
            "El archivo SHA-256 tiene formato invalido."
        )

    actual = sha256_file(manifest_file)

    if actual != match.group("digest"):
        raise ReleaseManifestError(
            "El checksum del manifiesto no coincide."
        )

    return actual


def load_verified_manifest(
    manifest_path,
    checksum_path,
    expected_repository,
    expected_tag="",
):
    verify_checksum(manifest_path, checksum_path)
    manifest_file = required_regular_file(
        manifest_path,
        "recovery-manifest.json",
    )

    try:
        payload = json.loads(
            manifest_file.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseManifestError(
            f"El manifiesto no contiene JSON valido: "
            f"{exc.__class__.__name__}."
        ) from exc

    return validate_manifest(
        payload,
        expected_repository=expected_repository,
        expected_tag=expected_tag,
    )


def build_parser():
    parser = argparse.ArgumentParser(
        description="Genera o valida un manifiesto de recovery de release.",
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("--repository", required=True)
    create_parser.add_argument("--release-tag", required=True)
    create_parser.add_argument("--source-commit", required=True)
    create_parser.add_argument("--app-image", required=True)
    create_parser.add_argument("--backup-image", required=True)
    create_parser.add_argument("--rto-seconds", required=True)
    create_parser.add_argument(
        "--output",
        default="recovery-manifest.json",
    )
    create_parser.add_argument(
        "--checksum-output",
        default="recovery-manifest.sha256",
    )

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument(
        "--manifest",
        default="recovery-manifest.json",
    )
    verify_parser.add_argument(
        "--checksum",
        default="recovery-manifest.sha256",
    )
    verify_parser.add_argument("--expected-repository", required=True)
    verify_parser.add_argument("--expected-tag", default="")
    return parser


def main():
    arguments = build_parser().parse_args()

    try:
        if arguments.action == "create":
            manifest = build_manifest(
                repository=arguments.repository,
                release_tag=arguments.release_tag,
                source_commit=arguments.source_commit,
                app_image=arguments.app_image,
                backup_image=arguments.backup_image,
                rto_seconds=arguments.rto_seconds,
            )
            write_manifest(arguments.output, manifest)
            write_checksum(arguments.checksum_output, arguments.output)
        else:
            manifest = load_verified_manifest(
                manifest_path=arguments.manifest,
                checksum_path=arguments.checksum,
                expected_repository=arguments.expected_repository,
                expected_tag=arguments.expected_tag,
            )
    except (OSError, ReleaseManifestError, ValueError) as exc:
        print(
            json.dumps(
                {"status": "critical", "error": str(exc)},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1

    print(
        json.dumps(
            {"status": "ok", "manifest": manifest},
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
