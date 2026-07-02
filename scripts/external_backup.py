#!/usr/bin/env python3
"""
Copia backups locales a un repositorio Restic cifrado y verifica restauracion.
El destino puede ser local, S3 compatible, REST u otro backend de Restic.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

SCRIPT_DIRECTORY = Path(__file__).resolve().parent

if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

from monitor_backups import (
    BACKUP_ID_PATTERN,
    REQUIRED_FILES,
    sha256_file,
    verify_backup,
)


DEFAULT_TAG = "vapes-shop"
INIT_CONFIRMATION = "INIT-EXTERNAL-BACKUP"
RECOVERY_CONFIRMATION = "RECOVER-LATEST-EXTERNAL-BACKUP"
CHECK_SUBSET_PATTERN = re.compile(r"^(100%|[1-9][0-9]?%|[1-9][0-9]*/[1-9][0-9]*)$")


class ExternalBackupError(RuntimeError):
    """Error esperado durante una operacion de backup externo."""


class CommandRunner:
    def __init__(self, timeout=3600):
        self.timeout = timeout

    def run(self, command, cwd=None):
        completed = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=self.timeout,
            cwd=cwd,
        )

        if completed.returncode != 0:
            error = completed.stderr.strip() or completed.stdout.strip()
            raise ExternalBackupError(
                f"Restic fallo con codigo {completed.returncode}: {error}"
            )

        return completed.stdout


def env_bool(name, default=False):
    raw_value = os.environ.get(name)

    if raw_value is None:
        return default

    value = raw_value.strip().lower()

    if value in {"1", "true", "yes", "on"}:
        return True

    if value in {"0", "false", "no", "off"}:
        return False

    raise ExternalBackupError(f"{name} debe ser true o false.")


def env_non_negative_int(name, default):
    raw_value = os.environ.get(name, str(default)).strip()

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ExternalBackupError(f"{name} debe ser un entero.") from exc

    if value < 0:
        raise ExternalBackupError(
            f"{name} debe ser mayor o igual a cero."
        )

    return value


def env_positive_int(name, default):
    value = env_non_negative_int(name, default)

    if value < 1:
        raise ExternalBackupError(f"{name} debe ser mayor que cero.")

    return value


def required_regular_file(value, label):
    if not value:
        raise ExternalBackupError(f"Falta {label}.")

    path = Path(value)

    if path.is_symlink() or not path.is_file():
        raise ExternalBackupError(f"{label} debe ser un archivo regular.")

    return path


def validate_secret_files():
    repository_file = required_regular_file(
        os.environ.get("RESTIC_REPOSITORY_FILE", ""),
        "RESTIC_REPOSITORY_FILE",
    )
    password_file = required_regular_file(
        os.environ.get("RESTIC_PASSWORD_FILE", ""),
        "RESTIC_PASSWORD_FILE",
    )
    repository = repository_file.read_text(encoding="utf-8").strip()
    password = password_file.read_text(encoding="utf-8").rstrip("\r\n")
    minimum_length = env_non_negative_int(
        "EXTERNAL_BACKUP_MIN_PASSWORD_LENGTH",
        20,
    )

    if not repository:
        raise ExternalBackupError("RESTIC_REPOSITORY_FILE esta vacio.")

    if len(password) < minimum_length:
        raise ExternalBackupError(
            "La clave Restic es menor que EXTERNAL_BACKUP_MIN_PASSWORD_LENGTH."
        )

    if "://" in repository:
        parsed = urlsplit(repository.split(":", 1)[-1])

        if parsed.username or parsed.password:
            raise ExternalBackupError(
                "El repositorio no debe incluir credenciales en la URL."
            )

    return {
        "repository_file": str(repository_file),
        "password_file": str(password_file),
    }


def parse_backup_summary(output):
    summary = None

    for raw_line in output.splitlines():
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            continue

        if (
            isinstance(event, dict)
            and event.get("message_type") == "summary"
        ):
            summary = event

    snapshot_id = (summary or {}).get("snapshot_id", "")

    if not re.fullmatch(r"[0-9a-f]{8,64}", snapshot_id):
        raise ExternalBackupError(
            "Restic no devolvio un snapshot_id valido."
        )

    return snapshot_id, summary


def parse_latest_snapshot(output):
    try:
        snapshots = json.loads(output)
    except json.JSONDecodeError as exc:
        raise ExternalBackupError(
            "Restic no devolvio snapshots JSON validos."
        ) from exc

    if not isinstance(snapshots, list) or len(snapshots) != 1:
        raise ExternalBackupError(
            "No existe exactamente un ultimo snapshot externo."
        )

    snapshot_id = snapshots[0].get("id", "")

    if not re.fullmatch(r"[0-9a-f]{8,64}", snapshot_id):
        raise ExternalBackupError(
            "El ultimo snapshot externo tiene un id invalido."
        )

    return snapshot_id


def load_local_backup(backup_root):
    root = Path(backup_root).resolve()
    latest_path = root / "latest.txt"

    if latest_path.is_symlink() or not latest_path.is_file():
        raise ExternalBackupError("No existe latest.txt en BACKUP_ROOT.")

    backup_id = latest_path.read_text(encoding="ascii").strip()

    if not BACKUP_ID_PATTERN.fullmatch(backup_id):
        raise ExternalBackupError("latest.txt contiene un backup_id invalido.")

    backup_directory = root / backup_id

    if backup_directory.is_symlink() or not backup_directory.is_dir():
        raise ExternalBackupError(
            "El directorio del backup local no es valido."
        )

    verify_backup(
        backup_root=root,
        max_age_hours=float(
            os.environ.get("BACKUP_MAX_AGE_HOURS", "26")
        ),
        future_tolerance_minutes=int(
            os.environ.get("BACKUP_FUTURE_TOLERANCE_MINUTES", "5")
        ),
        min_database_bytes=int(
            os.environ.get("BACKUP_MIN_DATABASE_BYTES", "128")
        ),
        min_media_bytes=int(
            os.environ.get("BACKUP_MIN_MEDIA_BYTES", "32")
        ),
        min_free_bytes=0,
        min_free_percent=0,
        min_free_copies=0,
    )
    return root, latest_path, backup_id, backup_directory


def compare_files(source, restored):
    for name in REQUIRED_FILES:
        source_path = source / name
        restored_path = restored / name

        if restored_path.is_symlink() or not restored_path.is_file():
            raise ExternalBackupError(
                f"La restauracion externa no contiene {name}."
            )

        if sha256_file(source_path) != sha256_file(restored_path):
            raise ExternalBackupError(
                f"La restauracion externa altero {name}."
            )


def inspect_restored_root(
    restored_root,
    expected_backup_id="",
    source_backup_directory=None,
):
    restored_root = Path(restored_root)
    restored_latest = restored_root / "latest.txt"

    if restored_latest.is_symlink() or not restored_latest.is_file():
        raise ExternalBackupError(
            "La restauracion externa no contiene latest.txt."
        )

    restored_backup_id = restored_latest.read_text(
        encoding="ascii"
    ).strip()

    if not BACKUP_ID_PATTERN.fullmatch(restored_backup_id):
        raise ExternalBackupError(
            "La restauracion externa contiene un backup_id invalido."
        )

    if expected_backup_id and restored_backup_id != expected_backup_id:
        raise ExternalBackupError(
            "La restauracion externa no corresponde al backup esperado."
        )

    restored_backup_directory = restored_root / restored_backup_id

    if (
        restored_backup_directory.is_symlink()
        or not restored_backup_directory.is_dir()
    ):
        raise ExternalBackupError(
            "La restauracion externa no contiene el backup esperado."
        )

    if source_backup_directory is not None:
        compare_files(
            Path(source_backup_directory),
            restored_backup_directory,
        )

    verification = verify_backup(
        backup_root=restored_root,
        max_age_hours=float(
            os.environ.get("BACKUP_MAX_AGE_HOURS", "26")
        ),
        future_tolerance_minutes=int(
            os.environ.get("BACKUP_FUTURE_TOLERANCE_MINUTES", "5")
        ),
        min_database_bytes=int(
            os.environ.get("BACKUP_MIN_DATABASE_BYTES", "128")
        ),
        min_media_bytes=int(
            os.environ.get("BACKUP_MIN_MEDIA_BYTES", "32")
        ),
        min_free_bytes=0,
        min_free_percent=0,
        min_free_copies=0,
    )
    return {
        "backup_id": restored_backup_id,
        "backup_directory": restored_backup_directory,
        "restored_backup_bytes": verification["backup_bytes"],
        "restored_media_members": verification["media_members"],
    }


def verify_restored_snapshot(
    runner,
    snapshot_id,
    restore_parent,
    expected_backup_id="",
    source_backup_directory=None,
):
    restore_parent = Path(
        os.path.abspath(os.fspath(restore_parent))
    )
    if restore_parent.is_symlink() or restore_parent.parent.is_symlink():
        raise ExternalBackupError(
            "EXTERNAL_BACKUP_RESTORE_ROOT no puede ser un enlace simbolico."
        )

    if restore_parent.exists() and not restore_parent.is_dir():
        raise ExternalBackupError(
            "EXTERNAL_BACKUP_RESTORE_ROOT debe ser un directorio regular."
        )

    restore_parent.mkdir(parents=True, exist_ok=True)

    if not restore_parent.is_dir():
        raise ExternalBackupError(
            "EXTERNAL_BACKUP_RESTORE_ROOT debe ser un directorio regular."
        )

    with tempfile.TemporaryDirectory(
        prefix="restic-restore-",
        dir=restore_parent,
    ) as temporary_directory:
        runner.run(
            [
                "restic",
                "restore",
                snapshot_id,
                "--target",
                temporary_directory,
            ]
        )
        restored_root = Path(temporary_directory)
        inspection = inspect_restored_root(
            restored_root,
            expected_backup_id=expected_backup_id,
            source_backup_directory=source_backup_directory,
        )

    return {
        "snapshot_id": snapshot_id,
        "backup_id": inspection["backup_id"],
        "restored_backup_bytes": inspection["restored_backup_bytes"],
        "restored_media_members": inspection["restored_media_members"],
    }


def check_repository(runner):
    subset = os.environ.get(
        "EXTERNAL_BACKUP_CHECK_SUBSET",
        "5%",
    ).strip()

    if not CHECK_SUBSET_PATTERN.fullmatch(subset):
        raise ExternalBackupError(
            "EXTERNAL_BACKUP_CHECK_SUBSET debe ser porcentaje o fraccion."
        )

    runner.run(["restic", "check", f"--read-data-subset={subset}"])
    return subset


def retention_command():
    daily = env_non_negative_int("EXTERNAL_BACKUP_KEEP_DAILY", 14)
    weekly = env_non_negative_int("EXTERNAL_BACKUP_KEEP_WEEKLY", 8)
    monthly = env_non_negative_int("EXTERNAL_BACKUP_KEEP_MONTHLY", 12)

    if not any((daily, weekly, monthly)):
        raise ExternalBackupError(
            "La retencion externa debe conservar al menos una copia."
        )

    host = os.environ.get(
        "EXTERNAL_BACKUP_HOST",
        "vapes-shop",
    ).strip()

    if not host or len(host) > 128:
        raise ExternalBackupError("EXTERNAL_BACKUP_HOST es invalido.")

    return [
        "restic",
        "forget",
        "--host",
        host,
        "--tag",
        DEFAULT_TAG,
        "--keep-daily",
        str(daily),
        "--keep-weekly",
        str(weekly),
        "--keep-monthly",
        str(monthly),
        "--prune",
    ], {
        "daily": daily,
        "weekly": weekly,
        "monthly": monthly,
    }


def initialize_repository(runner, confirmation):
    if confirmation != INIT_CONFIRMATION:
        raise ExternalBackupError(
            f"Confirma con --confirm {INIT_CONFIRMATION}."
        )

    runner.run(["restic", "init"])
    return {
        "event": "external_backup",
        "status": "initialized",
    }


def create_external_backup(runner):
    root, latest_path, backup_id, backup_directory = load_local_backup(
        os.environ.get("BACKUP_ROOT", "/backups")
    )
    host = os.environ.get(
        "EXTERNAL_BACKUP_HOST",
        "vapes-shop",
    ).strip()

    if not host or len(host) > 128:
        raise ExternalBackupError("EXTERNAL_BACKUP_HOST es invalido.")

    output = runner.run(
        [
            "restic",
            "backup",
            backup_id,
            latest_path.name,
            "--host",
            host,
            "--tag",
            DEFAULT_TAG,
            "--tag",
            f"backup-id:{backup_id}",
            "--json",
        ],
        cwd=root,
    )
    snapshot_id, summary = parse_backup_summary(output)
    check_subset = check_repository(runner)
    restore_report = verify_restored_snapshot(
        runner,
        snapshot_id,
        os.environ.get(
            "EXTERNAL_BACKUP_RESTORE_ROOT",
            "/restore-check",
        ),
        expected_backup_id=backup_id,
        source_backup_directory=backup_directory,
    )
    forget_command, retention = retention_command()
    runner.run(forget_command)
    return {
        "event": "external_backup",
        "status": "stored_and_restored",
        "backup_id": backup_id,
        "snapshot_id": snapshot_id,
        "check_subset": check_subset,
        "retention": retention,
        "files_new": (summary or {}).get("files_new", 0),
        "data_added": (summary or {}).get("data_added", 0),
        **restore_report,
    }


def verify_latest_external_backup(runner):
    host = os.environ.get(
        "EXTERNAL_BACKUP_HOST",
        "vapes-shop",
    ).strip()

    if not host or len(host) > 128:
        raise ExternalBackupError("EXTERNAL_BACKUP_HOST es invalido.")

    snapshots = runner.run(
        [
            "restic",
            "snapshots",
            "--host",
            host,
            "--tag",
            DEFAULT_TAG,
            "--latest",
            "1",
            "--json",
        ]
    )
    snapshot_id = parse_latest_snapshot(snapshots)
    check_subset = check_repository(runner)
    restore_report = verify_restored_snapshot(
        runner,
        snapshot_id,
        os.environ.get(
            "EXTERNAL_BACKUP_RESTORE_ROOT",
            "/restore-check",
        ),
    )
    return {
        "event": "external_backup",
        "status": "verified",
        "check_subset": check_subset,
        **restore_report,
    }


def recover_latest_external_backup(runner, confirmation):
    if confirmation != RECOVERY_CONFIRMATION:
        raise ExternalBackupError(
            f"Confirma con --confirm {RECOVERY_CONFIRMATION}."
        )

    backup_root = Path(
        os.path.abspath(os.environ.get("BACKUP_ROOT", "/backups"))
    )

    if backup_root.is_symlink() or backup_root.parent.is_symlink():
        raise ExternalBackupError(
            "BACKUP_ROOT no puede ser un enlace simbolico."
        )

    if backup_root.exists() and not backup_root.is_dir():
        raise ExternalBackupError(
            "BACKUP_ROOT debe ser un directorio regular."
        )

    backup_root.mkdir(parents=True, exist_ok=True)

    if not backup_root.is_dir():
        raise ExternalBackupError(
            "BACKUP_ROOT debe ser un directorio regular."
        )

    if any(backup_root.iterdir()):
        raise ExternalBackupError(
            "BACKUP_ROOT debe estar vacio para una recuperacion externa."
        )

    host = os.environ.get(
        "EXTERNAL_BACKUP_HOST",
        "vapes-shop",
    ).strip()

    if not host or len(host) > 128:
        raise ExternalBackupError("EXTERNAL_BACKUP_HOST es invalido.")

    snapshots = runner.run(
        [
            "restic",
            "snapshots",
            "--host",
            host,
            "--tag",
            DEFAULT_TAG,
            "--latest",
            "1",
            "--json",
        ]
    )
    snapshot_id = parse_latest_snapshot(snapshots)
    check_subset = check_repository(runner)

    with tempfile.TemporaryDirectory(
        prefix=".external-recovery-",
        dir=backup_root,
    ) as temporary_directory:
        runner.run(
            [
                "restic",
                "restore",
                snapshot_id,
                "--target",
                temporary_directory,
            ]
        )
        restored_root = Path(temporary_directory)
        inspection = inspect_restored_root(restored_root)
        backup_id = inspection["backup_id"]
        restored_backup_directory = inspection["backup_directory"]
        destination = backup_root / backup_id
        latest_path = backup_root / "latest.txt"
        temporary_latest = backup_root / ".latest-recovery.tmp"

        if destination.exists() or destination.is_symlink():
            raise ExternalBackupError(
                "El backup recuperado ya existe en BACKUP_ROOT."
            )

        if (
            latest_path.exists()
            or latest_path.is_symlink()
            or temporary_latest.exists()
            or temporary_latest.is_symlink()
        ):
            raise ExternalBackupError(
                "El indice latest de backup externo no admite rutas "
                "preexistentes ni enlaces simbolicos."
            )

        temporary_latest.write_text(
            f"{backup_id}\n",
            encoding="ascii",
        )
        os.chmod(temporary_latest, 0o600)
        os.replace(restored_backup_directory, destination)

        try:
            os.replace(temporary_latest, latest_path)
        except OSError:
            os.replace(destination, restored_backup_directory)
            raise

    return {
        "event": "external_backup",
        "status": "recovered",
        "snapshot_id": snapshot_id,
        "backup_id": backup_id,
        "check_subset": check_subset,
        "restored_backup_bytes": inspection["restored_backup_bytes"],
        "restored_media_members": inspection["restored_media_members"],
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
        raise ExternalBackupError(
            "El reporte de backup externo no admite enlaces simbolicos "
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
        description="Gestiona copias externas cifradas con Restic.",
    )
    parser.add_argument(
        "action",
        choices=("init", "backup", "verify-latest", "recover-latest"),
    )
    parser.add_argument("--confirm", default="")
    parser.add_argument("--output", default="")
    return parser


def main():
    arguments = build_parser().parse_args()

    try:
        enabled = env_bool("EXTERNAL_BACKUP_ENABLED", default=False)

        if not enabled:
            report = {
                "event": "external_backup",
                "status": "skipped",
                "reason": "EXTERNAL_BACKUP_ENABLED=false",
            }
            exit_code = 0
        else:
            validate_secret_files()
            runner = CommandRunner(
                timeout=env_positive_int(
                    "EXTERNAL_BACKUP_COMMAND_TIMEOUT",
                    3600,
                )
            )

            if arguments.action == "init":
                report = initialize_repository(
                    runner,
                    arguments.confirm,
                )
            elif arguments.action == "backup":
                report = create_external_backup(runner)
            elif arguments.action == "recover-latest":
                report = recover_latest_external_backup(
                    runner,
                    arguments.confirm,
                )
            else:
                report = verify_latest_external_backup(runner)

            exit_code = 0
    except (
        ExternalBackupError,
        OSError,
        UnicodeError,
        ValueError,
        subprocess.SubprocessError,
    ) as exc:
        report = {
            "event": "external_backup",
            "status": "critical",
            "error": str(exc),
        }
        exit_code = 1

    write_report(arguments.output, report)
    print(
        json.dumps(report, ensure_ascii=False, separators=(",", ":")),
        file=sys.stdout if exit_code == 0 else sys.stderr,
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
