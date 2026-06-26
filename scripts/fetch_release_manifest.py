#!/usr/bin/env python3
"""Descarga y verifica los assets de recuperacion de una release."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIRECTORY = Path(__file__).resolve().parent

if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

from release_manifest import (
    ReleaseManifestError,
    load_verified_manifest,
    validate_release_tag,
    validate_repository,
)


ASSET_NAMES = (
    "recovery-manifest.json",
    "recovery-manifest.sha256",
)


class ReleaseFetchError(RuntimeError):
    """No fue posible obtener una release confiable."""


class CommandRunner:
    def run(self, command):
        try:
            completed = subprocess.run(
                command,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=300,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ReleaseFetchError(
                f"No fue posible ejecutar {command[0]}: "
                f"{exc.__class__.__name__}."
            ) from exc

        if completed.returncode != 0:
            error = completed.stderr.strip() or completed.stdout.strip()
            raise ReleaseFetchError(
                f"Fallo {' '.join(command[:3])}: {error}"
            )

        return completed.stdout


def prepare_output_directory(path):
    output_directory = Path(os.path.abspath(os.fspath(path)))

    if (
        output_directory.is_symlink()
        or output_directory.parent.is_symlink()
    ):
        raise ReleaseFetchError(
            "El directorio de salida no puede ser un enlace simbolico."
        )

    if output_directory.exists() and not output_directory.is_dir():
        raise ReleaseFetchError(
            "El destino debe ser un directorio regular."
        )

    created = not output_directory.exists()
    output_directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    os.chmod(output_directory, 0o700)

    if not output_directory.is_dir():
        raise ReleaseFetchError(
            "El destino debe ser un directorio regular."
        )

    if any(output_directory.iterdir()):
        raise ReleaseFetchError(
            "El directorio de salida debe estar vacio."
        )

    return output_directory, created


def cleanup_assets(output_directory, remove_directory=False):
    if remove_directory:
        shutil.rmtree(output_directory, ignore_errors=True)
        return

    for path in output_directory.iterdir():
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)


def validate_downloaded_assets(output_directory):
    entries = {entry.name for entry in output_directory.iterdir()}

    if entries != set(ASSET_NAMES):
        raise ReleaseFetchError(
            "GitHub no devolvio exactamente los dos assets esperados."
        )

    for name in ASSET_NAMES:
        path = output_directory / name

        if path.is_symlink() or not path.is_file():
            raise ReleaseFetchError(
                f"El asset {name} no es un archivo regular."
            )


def fetch_release_manifest(
    repository,
    release_tag,
    output_directory,
    runner=None,
):
    runner = runner or CommandRunner()

    try:
        repository = validate_repository(repository)
        release_tag = validate_release_tag(release_tag)
    except ReleaseManifestError as exc:
        raise ReleaseFetchError(str(exc)) from exc

    output_directory, created = prepare_output_directory(
        output_directory
    )

    try:
        command = [
            "gh",
            "release",
            "download",
            release_tag,
            "--repo",
            repository,
            "--pattern",
            ASSET_NAMES[0],
            "--pattern",
            ASSET_NAMES[1],
            "--dir",
            str(output_directory),
        ]
        runner.run(command)
        validate_downloaded_assets(output_directory)
        manifest_path = output_directory / ASSET_NAMES[0]
        checksum_path = output_directory / ASSET_NAMES[1]
        runner.run(
            [
                "gh",
                "attestation",
                "verify",
                str(manifest_path),
                "--repo",
                repository,
            ]
        )
        manifest = load_verified_manifest(
            manifest_path=manifest_path,
            checksum_path=checksum_path,
            expected_repository=repository,
            expected_tag=release_tag,
        )
        os.chmod(manifest_path, 0o600)
        os.chmod(checksum_path, 0o600)
        return {
            "status": "verified",
            "repository": repository,
            "release_tag": release_tag,
            "source_commit": manifest["source_commit"],
            "manifest": str(manifest_path),
            "checksum": str(checksum_path),
            "app_image": manifest["images"]["application"],
            "backup_image": manifest["images"]["operations"],
        }
    except (
        OSError,
        ReleaseFetchError,
        ReleaseManifestError,
        subprocess.SubprocessError,
    ):
        cleanup_assets(output_directory, remove_directory=created)
        raise


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Descarga y verifica un manifiesto de recuperacion publicado."
        ),
    )
    parser.add_argument("--repository", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser


def main():
    arguments = build_parser().parse_args()

    try:
        report = fetch_release_manifest(
            repository=arguments.repository,
            release_tag=arguments.release_tag,
            output_directory=arguments.output_dir,
        )
        exit_code = 0
    except (
        OSError,
        ReleaseFetchError,
        ReleaseManifestError,
        subprocess.SubprocessError,
    ) as exc:
        report = {"status": "critical", "error": str(exc)}
        exit_code = 1

    print(
        json.dumps(report, ensure_ascii=False, separators=(",", ":")),
        file=sys.stdout if exit_code == 0 else sys.stderr,
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
