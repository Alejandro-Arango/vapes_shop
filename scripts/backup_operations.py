#!/usr/bin/env python3
"""
Ejecuta ciclos programados de backup y simulacros medibles de RPO/RTO.
Comparte el lock del despliegue para evitar migraciones concurrentes.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIRECTORY = Path(__file__).resolve().parent

if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

from deploy_production import validate_image_reference
from monitor_backups import (
    BackupMonitorError,
    send_webhook,
    validate_webhook_url,
)


class BackupOperationError(RuntimeError):
    """Fallo controlado del ciclo o simulacro de recuperacion."""


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00",
        "Z",
    )


def parse_json_output(output, label):
    for raw_line in reversed(output.splitlines()):
        line = raw_line.strip()

        if not line:
            continue

        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue

        if isinstance(payload, dict):
            return payload

    raise BackupOperationError(f"{label} no devolvio un reporte JSON.")


def env_bool(name, default):
    raw_value = os.environ.get(name)

    if raw_value is None:
        return default

    value = raw_value.strip().lower()

    if value in {"1", "true", "yes", "on"}:
        return True

    if value in {"0", "false", "no", "off"}:
        return False

    raise BackupOperationError(f"{name} debe ser true o false.")


class CommandRunner:
    """Ejecuta Docker Compose sin shell y conserva salida para los reportes."""

    def run(self, command, environment, timeout):
        try:
            completed = subprocess.run(
                command,
                env=environment,
                cwd=None,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise BackupOperationError(
                f"No fue posible ejecutar {command[0]}: "
                f"{exc.__class__.__name__}."
            ) from exc

        if completed.returncode != 0:
            error = completed.stderr.strip() or completed.stdout.strip()
            raise BackupOperationError(
                f"Fallo {' '.join(command)}: {error}"
            )

        return completed.stdout


class BackupOperationsController:
    def __init__(
        self,
        project_root,
        env_file,
        state_directory,
        runner=None,
        command_timeout=7200,
        wait_timeout=180,
        monotonic=time.monotonic,
    ):
        self.project_root = Path(project_root).resolve()
        self.env_file = Path(env_file).resolve()
        state_directory_path = Path(
            os.path.abspath(os.fspath(state_directory))
        )

        if (
            state_directory_path.is_symlink()
            or state_directory_path.parent.is_symlink()
        ):
            raise BackupOperationError(
                "El directorio de estado de backups no admite "
                "enlaces simbolicos."
            )

        self.state_directory = state_directory_path
        self.current_state_path = self.state_directory / "current.json"
        self.lock_directory = self.state_directory.with_name(
            f"{self.state_directory.name}.lock"
        )
        self.runner = runner or CommandRunner()
        self.command_timeout = command_timeout
        self.wait_timeout = wait_timeout
        self.monotonic = monotonic

    def verify_files(self):
        required_paths = (
            self.env_file,
            self.project_root / "compose.yaml",
            self.project_root / "compose.production.yaml",
            self.current_state_path,
        )

        for required_path in required_paths:
            if not required_path.is_file():
                raise BackupOperationError(
                    f"No existe el archivo requerido: {required_path}"
                )

    def load_state(self):
        try:
            state = json.loads(
                self.current_state_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise BackupOperationError(
                f"Estado invalido: {self.current_state_path}"
            ) from exc

        if not isinstance(state, dict):
            raise BackupOperationError(
                f"Estado invalido: {self.current_state_path}"
            )

        try:
            app_image = validate_image_reference(
                state.get("app_image", ""),
                "app_image",
            )
            backup_image = validate_image_reference(
                state.get("backup_image", ""),
                "backup_image",
            )
        except RuntimeError as exc:
            raise BackupOperationError(str(exc)) from exc

        return {
            "app_image": app_image,
            "backup_image": backup_image,
        }

    def acquire_lock(self):
        try:
            self.lock_directory.mkdir(parents=False)
        except FileExistsError as exc:
            raise BackupOperationError(
                f"Existe otra operacion activa: {self.lock_directory}"
            ) from exc

    def release_lock(self):
        try:
            self.lock_directory.rmdir()
        except FileNotFoundError:
            pass

    def compose_command(self, *arguments):
        return [
            "docker",
            "compose",
            "--project-directory",
            str(self.project_root),
            "--env-file",
            str(self.env_file),
            "--file",
            str(self.project_root / "compose.yaml"),
            "--file",
            str(self.project_root / "compose.production.yaml"),
            *arguments,
        ]

    def environment(self, state):
        environment = os.environ.copy()
        environment["APP_IMAGE"] = state["app_image"]
        environment["BACKUP_IMAGE"] = state["backup_image"]
        return environment

    def run_compose(self, state, *arguments):
        return self.runner.run(
            self.compose_command(*arguments),
            self.environment(state),
            self.command_timeout,
        )

    def prepare(self, state):
        self.run_compose(state, "config", "--quiet")

    def start_database(self, state):
        self.run_compose(
            state,
            "up",
            "--detach",
            "--wait",
            "--wait-timeout",
            str(self.wait_timeout),
            "db",
        )

    def run_local_backup(self, state):
        self.run_compose(
            state,
            "run",
            "--rm",
            "--no-deps",
            "backup",
        )

    def monitor_local_backup(self, state):
        output = self.run_compose(
            state,
            "run",
            "--rm",
            "--no-deps",
            "backup-monitor",
        )
        report = parse_json_output(output, "backup-monitor")

        if report.get("status") != "ok":
            raise BackupOperationError(
                "backup-monitor no reporto estado saludable."
            )

        return report

    def run_external_backup(self, state, action):
        output = self.run_compose(
            state,
            "run",
            "--rm",
            "--no-deps",
            "external-backup",
            action,
        )
        report = parse_json_output(output, "external-backup")
        status = report.get("status")

        if status == "skipped":
            if env_bool("BACKUP_REQUIRE_EXTERNAL", True):
                raise BackupOperationError(
                    "La copia externa es obligatoria y fue omitida."
                )

            return report

        expected_status = (
            "stored_and_restored"
            if action == "backup"
            else "verified"
        )

        if status != expected_status:
            raise BackupOperationError(
                f"external-backup no reporto {expected_status}."
            )

        return report

    @staticmethod
    def assert_rpo(local_report, external_report, rpo_hours):
        try:
            age_hours = float(local_report["age_hours"])
        except (KeyError, TypeError, ValueError) as exc:
            raise BackupOperationError(
                "backup-monitor no reporto age_hours valido."
            ) from exc

        if age_hours > rpo_hours:
            raise BackupOperationError(
                f"RPO incumplido: {age_hours:.3f} h > {rpo_hours:.3f} h."
            )

        if external_report.get("status") != "skipped":
            if (
                external_report.get("backup_id")
                != local_report.get("backup_id")
            ):
                raise BackupOperationError(
                    "El snapshot externo no corresponde al ultimo backup local."
                )

        return age_hours

    def cycle(self, rpo_hours):
        self.verify_files()
        state = self.load_state()
        self.acquire_lock()
        started_at = self.monotonic()

        try:
            self.prepare(state)
            self.start_database(state)
            self.run_local_backup(state)
            local_report = self.monitor_local_backup(state)
            external_report = self.run_external_backup(state, "backup")
            age_hours = self.assert_rpo(
                local_report,
                external_report,
                rpo_hours,
            )
            elapsed = self.monotonic() - started_at
            return {
                "event": "backup_cycle",
                "status": "ok",
                "checked_at": utc_now(),
                "backup_id": local_report["backup_id"],
                "snapshot_id": external_report.get("snapshot_id", ""),
                "rpo_objective_hours": rpo_hours,
                "rpo_actual_hours": round(age_hours, 3),
                "elapsed_seconds": round(elapsed, 3),
                "external_status": external_report["status"],
            }
        finally:
            self.release_lock()

    def drill(self, rpo_hours, rto_seconds):
        self.verify_files()
        state = self.load_state()
        self.acquire_lock()

        try:
            self.prepare(state)
            local_report = self.monitor_local_backup(state)
            restore_started_at = self.monotonic()
            external_report = self.run_external_backup(
                state,
                "verify-latest",
            )
            restore_elapsed = self.monotonic() - restore_started_at
            age_hours = self.assert_rpo(
                local_report,
                external_report,
                rpo_hours,
            )

            if restore_elapsed > rto_seconds:
                raise BackupOperationError(
                    "RTO incumplido: "
                    f"{restore_elapsed:.3f} s > {rto_seconds:.3f} s."
                )

            return {
                "event": "recovery_drill",
                "status": "ok",
                "checked_at": utc_now(),
                "backup_id": local_report["backup_id"],
                "snapshot_id": external_report.get("snapshot_id", ""),
                "rpo_objective_hours": rpo_hours,
                "rpo_actual_hours": round(age_hours, 3),
                "rto_objective_seconds": rto_seconds,
                "rto_actual_seconds": round(restore_elapsed, 3),
                "external_status": external_report["status"],
            }
        finally:
            self.release_lock()


def positive_float(value):
    parsed = float(value)

    if parsed <= 0:
        raise argparse.ArgumentTypeError("debe ser mayor que 0")

    return parsed


def positive_integer(value):
    parsed = int(value)

    if parsed < 1:
        raise argparse.ArgumentTypeError("debe ser mayor o igual a 1")

    return parsed


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
        raise BackupOperationError(
            "El reporte de backup no admite enlaces simbolicos."
        )

    temporary_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary_path, 0o600)
    os.replace(temporary_path, output_path)


def alert_failure(report):
    webhook_url = os.environ.get("MONITOR_WEBHOOK_URL", "").strip()

    if not webhook_url:
        report["alert"] = "not_configured"
        return

    try:
        send_webhook(
            validate_webhook_url(webhook_url),
            os.environ.get("MONITOR_WEBHOOK_TOKEN", ""),
            report,
            float(os.environ.get("BACKUP_ALERT_TIMEOUT", "10")),
        )
        report["alert"] = "sent"
    except (BackupMonitorError, ValueError) as exc:
        report["alert"] = "failed"
        report["alert_error"] = str(exc)


def build_parser():
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Ejecuta backups programados y simulacros RPO/RTO.",
    )
    parser.add_argument("action", choices=("cycle", "drill"))
    parser.add_argument(
        "--project-root",
        default=str(project_root),
    )
    parser.add_argument(
        "--env-file",
        default=str(project_root / "compose.production.env"),
    )
    parser.add_argument(
        "--state-dir",
        default=str(project_root / ".deploy"),
    )
    parser.add_argument(
        "--rpo-hours",
        type=positive_float,
        default=float(os.environ.get("BACKUP_RPO_HOURS", "26")),
    )
    parser.add_argument(
        "--rto-seconds",
        type=positive_float,
        default=float(os.environ.get("BACKUP_RTO_SECONDS", "900")),
    )
    parser.add_argument(
        "--command-timeout",
        type=positive_integer,
        default=int(os.environ.get("BACKUP_OPERATION_TIMEOUT", "7200")),
    )
    parser.add_argument(
        "--wait-timeout",
        type=positive_integer,
        default=180,
    )
    parser.add_argument("--output", default="")
    return parser


def main():
    arguments = build_parser().parse_args()
    controller = BackupOperationsController(
        project_root=arguments.project_root,
        env_file=arguments.env_file,
        state_directory=arguments.state_dir,
        command_timeout=arguments.command_timeout,
        wait_timeout=arguments.wait_timeout,
    )

    try:
        if arguments.action == "cycle":
            report = controller.cycle(arguments.rpo_hours)
        else:
            report = controller.drill(
                arguments.rpo_hours,
                arguments.rto_seconds,
            )

        exit_code = 0
    except BackupOperationError as exc:
        report = {
            "event": (
                "backup_cycle"
                if arguments.action == "cycle"
                else "recovery_drill"
            ),
            "status": "critical",
            "checked_at": utc_now(),
            "error": str(exc),
        }
        alert_failure(report)
        exit_code = 1

    write_report(arguments.output, report)
    print(
        json.dumps(report, ensure_ascii=False, separators=(",", ":")),
        file=sys.stdout if exit_code == 0 else sys.stderr,
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
