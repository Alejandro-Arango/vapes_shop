#!/usr/bin/env python3
"""Recupera el servicio completo desde el ultimo snapshot externo."""

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

from deploy_production import load_health_host, validate_image_reference
from monitor_backups import (
    BackupMonitorError,
    send_webhook,
    validate_webhook_url,
)
from release_manifest import (
    ReleaseManifestError,
    load_verified_manifest,
    validate_commit,
    validate_release_tag,
)


RECOVERY_CONFIRMATION = "RECOVER-PRODUCTION-FROM-EXTERNAL-BACKUP"
EXTERNAL_RECOVERY_CONFIRMATION = "RECOVER-LATEST-EXTERNAL-BACKUP"
BREAK_GLASS_CONFIRMATION = "USE-MANUAL-RECOVERY-IMAGES"
MIN_BREAK_GLASS_REASON_LENGTH = 12
MAX_BREAK_GLASS_REASON_LENGTH = 200


class ProductionRecoveryError(RuntimeError):
    """Fallo controlado durante una recuperacion productiva."""


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

    raise ProductionRecoveryError(
        f"{label} no devolvio un reporte JSON."
    )


def load_rto_objective(env_file, default=1800.0):
    try:
        lines = Path(env_file).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ProductionRecoveryError(
            f"No fue posible leer el entorno productivo: "
            f"{exc.__class__.__name__}."
        ) from exc

    raw_value = ""

    for raw_line in lines:
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)

        if key == "DISASTER_RECOVERY_RTO_SECONDS":
            raw_value = value.strip().strip('"').strip("'")
            break

    if not raw_value:
        return default

    try:
        objective = float(raw_value)
    except ValueError as exc:
        raise ProductionRecoveryError(
            "DISASTER_RECOVERY_RTO_SECONDS debe ser numerico."
        ) from exc

    if objective <= 0:
        raise ProductionRecoveryError(
            "DISASTER_RECOVERY_RTO_SECONDS debe ser mayor que cero."
        )

    return objective


def validate_break_glass_reason(value):
    normalized_reason = value.strip()

    if "\n" in normalized_reason or "\r" in normalized_reason:
        raise ProductionRecoveryError(
            "--break-glass-reason debe ocupar una sola linea."
        )

    if not (
        MIN_BREAK_GLASS_REASON_LENGTH
        <= len(normalized_reason)
        <= MAX_BREAK_GLASS_REASON_LENGTH
    ):
        raise ProductionRecoveryError(
            "--break-glass-reason debe tener entre "
            f"{MIN_BREAK_GLASS_REASON_LENGTH} y "
            f"{MAX_BREAK_GLASS_REASON_LENGTH} caracteres."
        )

    return normalized_reason


def validate_recovery_provenance(
    source_mode,
    release_tag="",
    source_commit="",
    break_glass_reason="",
):
    if source_mode == "verified-manifest":
        if break_glass_reason:
            raise ProductionRecoveryError(
                "verified-manifest no admite un motivo break-glass."
            )

        try:
            validated_tag = validate_release_tag(release_tag)
            validated_commit = validate_commit(source_commit)
        except ReleaseManifestError as exc:
            raise ProductionRecoveryError(str(exc)) from exc

        return {
            "source_mode": source_mode,
            "release_tag": validated_tag,
            "source_commit": validated_commit,
            "break_glass_reason": "",
        }

    if source_mode == "manual-break-glass":
        if release_tag or source_commit:
            raise ProductionRecoveryError(
                "manual-break-glass no admite identidad de manifiesto."
            )

        return {
            "source_mode": source_mode,
            "release_tag": "",
            "source_commit": "",
            "break_glass_reason": validate_break_glass_reason(
                break_glass_reason
            ),
        }

    raise ProductionRecoveryError(
        "source_mode debe ser verified-manifest o manual-break-glass."
    )


def build_failure_report(error, source=None):
    report = {
        "event": "production_disaster_recovery",
        "status": "critical",
        "checked_at": utc_now(),
        "error": str(error),
    }

    if not source:
        return report

    for key in (
        "source_mode",
        "app_image",
        "backup_image",
        "release_tag",
        "source_commit",
        "break_glass_reason",
    ):
        value = source.get(key)

        if value:
            report[key] = value

    return report


def load_recovery_source(
    app_image,
    backup_image,
    release_manifest="",
    manifest_checksum="",
    expected_repository="",
    expected_tag="",
    break_glass_confirmation="",
    break_glass_reason="",
):
    if release_manifest:
        if (
            app_image
            or backup_image
            or break_glass_confirmation
            or break_glass_reason
        ):
            raise ProductionRecoveryError(
                "No combines un manifiesto con parametros break-glass."
            )

        if not manifest_checksum or not expected_repository:
            raise ProductionRecoveryError(
                "El manifiesto requiere checksum y repositorio esperado."
            )

        try:
            manifest = load_verified_manifest(
                manifest_path=release_manifest,
                checksum_path=manifest_checksum,
                expected_repository=expected_repository,
                expected_tag=expected_tag,
            )
        except ReleaseManifestError as exc:
            raise ProductionRecoveryError(str(exc)) from exc

        return {
            "app_image": manifest["images"]["application"],
            "backup_image": manifest["images"]["operations"],
            "release_tag": manifest["release_tag"],
            "source_commit": manifest["source_commit"],
            "manifest_rto_seconds": manifest["recovery"]["rto_seconds"],
            "source_mode": "verified-manifest",
            "break_glass_reason": "",
        }

    if not app_image or not backup_image:
        raise ProductionRecoveryError(
            "--app-image y --backup-image son obligatorios sin manifiesto."
        )

    if break_glass_confirmation != BREAK_GLASS_CONFIRMATION:
        raise ProductionRecoveryError(
            "Las imagenes manuales requieren "
            f"--break-glass-confirm {BREAK_GLASS_CONFIRMATION}."
        )

    normalized_reason = validate_break_glass_reason(break_glass_reason)

    return {
        "app_image": app_image,
        "backup_image": backup_image,
        "release_tag": "",
        "source_commit": "",
        "manifest_rto_seconds": None,
        "source_mode": "manual-break-glass",
        "break_glass_reason": normalized_reason,
    }


class CommandRunner:
    def run(self, command, environment, timeout):
        try:
            completed = subprocess.run(
                command,
                env=environment,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ProductionRecoveryError(
                f"No fue posible ejecutar {command[0]}: "
                f"{exc.__class__.__name__}."
            ) from exc

        if completed.returncode != 0:
            error = completed.stderr.strip() or completed.stdout.strip()
            raise ProductionRecoveryError(
                f"Fallo {' '.join(command)}: {error}"
            )

        return completed.stdout


class ProductionRecoveryController:
    def __init__(
        self,
        project_root,
        env_file,
        state_directory,
        runner=None,
        command_timeout=7200,
        wait_timeout=300,
        monotonic=time.monotonic,
    ):
        self.project_root = Path(project_root).resolve()
        self.env_file = Path(env_file).resolve()
        self.state_directory = Path(state_directory).resolve()
        self.current_state_path = self.state_directory / "current.json"
        self.lock_directory = self.state_directory.with_name(
            f"{self.state_directory.name}.lock"
        )
        self.runner = runner or CommandRunner()
        self.command_timeout = command_timeout
        self.wait_timeout = wait_timeout
        self.monotonic = monotonic

    def verify_files(self):
        for required_path in (
            self.env_file,
            self.project_root / "compose.yaml",
            self.project_root / "compose.production.yaml",
        ):
            if not required_path.is_file():
                raise ProductionRecoveryError(
                    f"No existe el archivo requerido: {required_path}"
                )

        if self.current_state_path.exists():
            raise ProductionRecoveryError(
                "Ya existe estado productivo; usa despliegue o rollback."
            )

    def acquire_lock(self):
        try:
            self.lock_directory.mkdir(parents=False)
        except FileExistsError as exc:
            raise ProductionRecoveryError(
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

    @staticmethod
    def environment(state, extra=None):
        environment = os.environ.copy()
        environment["COMPOSE_PROJECT_NAME"] = "vapes-shop"
        environment["APP_IMAGE"] = state["app_image"]
        environment["BACKUP_IMAGE"] = state["backup_image"]
        environment.update(extra or {})
        return environment

    def run_compose(self, state, *arguments, extra_environment=None):
        return self.runner.run(
            self.compose_command(*arguments),
            self.environment(state, extra_environment),
            self.command_timeout,
        )

    def assert_clean_runtime(self, state):
        output = self.run_compose(
            state,
            "ps",
            "--all",
            "--services",
        )

        if output.strip():
            raise ProductionRecoveryError(
                "La recuperacion exige que no existan contenedores previos."
            )

        volume_output = self.runner.run(
            [
                "docker",
                "volume",
                "ls",
                "--quiet",
                "--filter",
                "label=com.docker.compose.project=vapes-shop",
            ],
            self.environment(state),
            self.command_timeout,
        )

        if volume_output.strip():
            raise ProductionRecoveryError(
                "La recuperacion exige que no existan volumenes previos."
            )

    def verify_source_checkout(self, state, source_commit):
        if not source_commit:
            return False

        common = [
            "git",
            "-C",
            str(self.project_root),
        ]
        inside_work_tree = self.runner.run(
            [
                *common,
                "rev-parse",
                "--is-inside-work-tree",
            ],
            self.environment(state),
            self.command_timeout,
        ).strip()

        if inside_work_tree != "true":
            raise ProductionRecoveryError(
                "PROJECT_ROOT no es un checkout Git valido."
            )

        checkout_commit = self.runner.run(
            [
                *common,
                "rev-parse",
                "HEAD",
            ],
            self.environment(state),
            self.command_timeout,
        ).strip().lower()

        if checkout_commit != source_commit.lower():
            raise ProductionRecoveryError(
                "El checkout local no coincide con source_commit "
                "del manifiesto."
            )

        tracked_changes = self.runner.run(
            [
                *common,
                "status",
                "--porcelain=v1",
                "--untracked-files=no",
            ],
            self.environment(state),
            self.command_timeout,
        ).strip()

        if tracked_changes:
            raise ProductionRecoveryError(
                "El checkout local contiene cambios rastreados."
            )

        return True

    def prepare(self, state):
        self.run_compose(state, "config", "--quiet")
        self.run_compose(
            state,
            "pull",
            "db",
            "migrate",
            "web",
            "proxy",
            "external-recovery",
            "restore",
        )

    def validate_application(self, state):
        for command in (
            ("python", "manage.py", "check", "--deploy"),
            ("python", "manage.py", "production_check"),
        ):
            self.run_compose(
                state,
                "run",
                "--rm",
                "--no-deps",
                "migrate",
                *command,
            )

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

    def recover_external_backup(self, state):
        output = self.run_compose(
            state,
            "run",
            "--rm",
            "--no-deps",
            "external-recovery",
            "recover-latest",
            "--confirm",
            EXTERNAL_RECOVERY_CONFIRMATION,
        )
        report = parse_json_output(output, "external-recovery")

        if report.get("status") != "recovered":
            raise ProductionRecoveryError(
                "external-recovery no reporto recovered."
            )

        return report

    def restore_data(self, state, backup_id):
        self.run_compose(
            state,
            "run",
            "--rm",
            "--no-deps",
            "restore",
            extra_environment={
                "RESTORE_BACKUP_ID": backup_id,
                "RESTORE_CONFIRM": f"RESTORE-{backup_id}",
                "RESTORE_CREATE_SAFETY_BACKUP": "false",
            },
        )

    def migrate(self, state):
        self.run_compose(
            state,
            "run",
            "--rm",
            "--no-deps",
            "migrate",
        )

    def start_application(self, state):
        health_host = load_health_host(self.env_file)
        headers = (
            "--header",
            f"Host: {health_host}",
            "--header",
            "X-Forwarded-Proto: https",
        )
        self.run_compose(
            state,
            "up",
            "--detach",
            "--no-build",
            "--no-deps",
            "--pull",
            "never",
            "--wait",
            "--wait-timeout",
            str(self.wait_timeout),
            "web",
            "proxy",
        )
        self.run_compose(
            state,
            "exec",
            "--no-tty",
            "proxy",
            "wget",
            "--quiet",
            "--spider",
            *headers,
            "http://127.0.0.1:8080/healthz",
        )
        catalog_output = self.run_compose(
            state,
            "exec",
            "--no-tty",
            "proxy",
            "wget",
            "--quiet",
            "--output-document=-",
            *headers,
            "http://127.0.0.1:8080/api/products/?page=1&page_size=1",
        )

        try:
            catalog = json.loads(catalog_output)
        except json.JSONDecodeError as exc:
            raise ProductionRecoveryError(
                "El catalogo recuperado no devolvio JSON valido."
            ) from exc

        if (
            not isinstance(catalog, dict)
            or not isinstance(catalog.get("results"), list)
        ):
            raise ProductionRecoveryError(
                "El catalogo recuperado no devolvio results."
            )

        return len(catalog["results"])

    def write_state(self, state):
        self.state_directory.mkdir(parents=True, exist_ok=True)
        temporary_path = self.current_state_path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps(state, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, self.current_state_path)

    def recover(
        self,
        app_image,
        backup_image,
        rto_seconds,
        release_tag="",
        source_commit="",
        source_mode="",
        break_glass_reason="",
    ):
        provenance = validate_recovery_provenance(
            source_mode=source_mode,
            release_tag=release_tag,
            source_commit=source_commit,
            break_glass_reason=break_glass_reason,
        )

        try:
            state = {
                "app_image": validate_image_reference(
                    app_image,
                    "APP_IMAGE",
                ),
                "backup_image": validate_image_reference(
                    backup_image,
                    "BACKUP_IMAGE",
                ),
            }
        except RuntimeError as exc:
            raise ProductionRecoveryError(str(exc)) from exc
        self.verify_files()
        self.acquire_lock()
        started_at = self.monotonic()

        try:
            source_verified = self.verify_source_checkout(
                state,
                provenance["source_commit"],
            )
            self.assert_clean_runtime(state)
            self.prepare(state)
            self.validate_application(state)
            self.start_database(state)
            external_report = self.recover_external_backup(state)
            backup_id = external_report.get("backup_id", "")
            snapshot_id = external_report.get("snapshot_id", "")

            if not backup_id or not snapshot_id:
                raise ProductionRecoveryError(
                    "external-recovery no reporto backup_id y snapshot_id."
                )

            self.restore_data(state, backup_id)
            self.migrate(state)
            recovered_products = self.start_application(state)
            elapsed = self.monotonic() - started_at
            recovered_state = {
                **state,
                "deployed_at": utc_now(),
                "recovered_from_backup": backup_id,
                "recovered_from_snapshot": snapshot_id,
                "source_mode": provenance["source_mode"],
            }

            if provenance["break_glass_reason"]:
                recovered_state["break_glass_reason"] = provenance[
                    "break_glass_reason"
                ]

            if provenance["release_tag"]:
                recovered_state["release_tag"] = provenance["release_tag"]

            if provenance["source_commit"]:
                recovered_state["source_commit"] = provenance[
                    "source_commit"
                ]

            self.write_state(recovered_state)
            report = {
                "event": "production_disaster_recovery",
                "status": "ok",
                "checked_at": utc_now(),
                "backup_id": backup_id,
                "snapshot_id": snapshot_id,
                "rto_objective_seconds": rto_seconds,
                "rto_actual_seconds": round(elapsed, 3),
                "catalog_probe_products": recovered_products,
                "source_checkout_verified": source_verified,
                "source_mode": provenance["source_mode"],
                **state,
            }

            if provenance["break_glass_reason"]:
                report["break_glass_reason"] = provenance[
                    "break_glass_reason"
                ]

            if provenance["release_tag"]:
                report["release_tag"] = provenance["release_tag"]

            if provenance["source_commit"]:
                report["source_commit"] = provenance["source_commit"]

            if elapsed > rto_seconds:
                report["status"] = "critical"
                report["error"] = (
                    "RTO integral incumplido: "
                    f"{elapsed:.3f} s > {rto_seconds:.3f} s."
                )

            return report
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

    if output_path.is_symlink() or output_path.parent.is_symlink():
        raise ProductionRecoveryError(
            "El reporte no puede reemplazar un enlace simbolico."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(f"{output_path.suffix}.tmp")
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
            timeout=float(
                os.environ.get("BACKUP_ALERT_TIMEOUT", "10")
            ),
        )
        report["alert"] = "sent"
    except (BackupMonitorError, OSError, ValueError) as exc:
        report["alert"] = f"failed:{exc.__class__.__name__}"


def build_parser():
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description=(
            "Recupera produccion desde el ultimo snapshot Restic externo."
        ),
    )
    parser.add_argument("--project-root", default=str(project_root))
    parser.add_argument(
        "--env-file",
        default=str(project_root / "compose.production.env"),
    )
    parser.add_argument(
        "--state-dir",
        default=str(project_root / ".deploy"),
    )
    parser.add_argument("--app-image", default=os.environ.get("APP_IMAGE", ""))
    parser.add_argument(
        "--backup-image",
        default=os.environ.get("BACKUP_IMAGE", ""),
    )
    parser.add_argument("--release-manifest", default="")
    parser.add_argument("--manifest-checksum", default="")
    parser.add_argument("--expected-repository", default="")
    parser.add_argument("--expected-tag", default="")
    parser.add_argument("--break-glass-confirm", default="")
    parser.add_argument("--break-glass-reason", default="")
    parser.add_argument(
        "--rto-seconds",
        type=positive_float,
        default=None,
    )
    parser.add_argument(
        "--command-timeout",
        type=positive_integer,
        default=7200,
    )
    parser.add_argument(
        "--wait-timeout",
        type=positive_integer,
        default=300,
    )
    parser.add_argument("--confirm", default="")
    parser.add_argument("--output", default="")
    return parser


def main():
    arguments = build_parser().parse_args()
    source = None

    try:
        if arguments.confirm != RECOVERY_CONFIRMATION:
            raise ProductionRecoveryError(
                f"Confirma con --confirm {RECOVERY_CONFIRMATION}."
            )

        source = load_recovery_source(
            app_image=arguments.app_image,
            backup_image=arguments.backup_image,
            release_manifest=arguments.release_manifest,
            manifest_checksum=arguments.manifest_checksum,
            expected_repository=arguments.expected_repository,
            expected_tag=arguments.expected_tag,
            break_glass_confirmation=arguments.break_glass_confirm,
            break_glass_reason=arguments.break_glass_reason,
        )

        controller = ProductionRecoveryController(
            project_root=arguments.project_root,
            env_file=arguments.env_file,
            state_directory=arguments.state_dir,
            command_timeout=arguments.command_timeout,
            wait_timeout=arguments.wait_timeout,
        )
        rto_seconds = arguments.rto_seconds

        if rto_seconds is None:
            rto_seconds = (
                source["manifest_rto_seconds"]
                if source["manifest_rto_seconds"] is not None
                else load_rto_objective(arguments.env_file)
            )

        report = controller.recover(
            app_image=source["app_image"],
            backup_image=source["backup_image"],
            rto_seconds=rto_seconds,
            release_tag=source["release_tag"],
            source_commit=source["source_commit"],
            source_mode=source["source_mode"],
            break_glass_reason=source["break_glass_reason"],
        )
        exit_code = 0 if report["status"] == "ok" else 1
    except (
        ProductionRecoveryError,
        OSError,
        ValueError,
        subprocess.SubprocessError,
    ) as exc:
        report = build_failure_report(exc, source)
        exit_code = 1

    if exit_code:
        alert_failure(report)

    write_report(arguments.output, report)
    print(
        json.dumps(report, ensure_ascii=False, separators=(",", ":")),
        file=sys.stdout if exit_code == 0 else sys.stderr,
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
