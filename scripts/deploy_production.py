#!/usr/bin/env python3
"""
Despliega imagenes inmutables con backup, readiness y rollback de aplicacion.
No revierte migraciones de base de datos automaticamente.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


DIGEST_IMAGE_PATTERN = re.compile(
    r"^[a-z0-9][a-z0-9.-]*(?::[0-9]+)?/"
    r"[a-z0-9][a-z0-9._/-]*(?::[a-zA-Z0-9._-]+)?"
    r"@sha256:[0-9a-f]{64}$"
)


class DeploymentError(RuntimeError):
    """Fallo controlado del proceso de despliegue."""


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00",
        "Z",
    )


def validate_image_reference(value, label):
    if not DIGEST_IMAGE_PATTERN.fullmatch(value):
        raise DeploymentError(
            f"{label} debe usar una referencia inmutable "
            "registry/repository@sha256:<64 hex>."
        )

    return value


class CommandRunner:
    """Ejecuta comandos sin shell para evitar interpolacion accidental."""

    def run(self, command, env):
        print(f"+ {' '.join(command)}", flush=True)
        try:
            completed = subprocess.run(
                command,
                env=env,
                check=False,
            )
        except OSError as exc:
            raise DeploymentError(
                f"No fue posible ejecutar {command[0]}: "
                f"{exc.__class__.__name__}."
            ) from exc

        if completed.returncode != 0:
            raise DeploymentError(
                f"Fallo el comando con codigo {completed.returncode}: "
                f"{' '.join(command)}"
            )


class DeploymentController:
    def __init__(
        self,
        project_root,
        env_file,
        state_directory,
        runner=None,
        wait_timeout=180,
    ):
        self.project_root = Path(project_root).resolve()
        self.env_file = Path(env_file).resolve()
        self.state_directory = Path(state_directory).resolve()
        self.lock_directory = self.state_directory.with_name(
            f"{self.state_directory.name}.lock"
        )
        self.runner = runner or CommandRunner()
        self.wait_timeout = wait_timeout

    @property
    def current_state_path(self):
        return self.state_directory / "current.json"

    @property
    def previous_state_path(self):
        return self.state_directory / "previous.json"

    def acquire_lock(self):
        try:
            self.lock_directory.mkdir(parents=False)
        except FileExistsError as exc:
            raise DeploymentError(
                f"Ya existe un despliegue activo: {self.lock_directory}"
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

    def deployment_environment(self, state):
        environment = os.environ.copy()
        environment["APP_IMAGE"] = state["app_image"]
        environment["BACKUP_IMAGE"] = state["backup_image"]
        return environment

    def run_compose(self, state, *arguments):
        self.runner.run(
            self.compose_command(*arguments),
            self.deployment_environment(state),
        )

    def load_state(self, path, required=False):
        if not path.exists():
            if required:
                raise DeploymentError(f"No existe el estado requerido: {path}")
            return None

        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DeploymentError(f"Estado invalido: {path}") from exc

        if not isinstance(state, dict):
            raise DeploymentError(f"Estado invalido: {path}")

        validate_image_reference(state.get("app_image", ""), "app_image")
        validate_image_reference(
            state.get("backup_image", ""),
            "backup_image",
        )
        return state

    def write_state(self, path, state):
        self.state_directory.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps(state, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary_path, path)

    def verify_files(self):
        required_paths = (
            self.env_file,
            self.project_root / "compose.yaml",
            self.project_root / "compose.production.yaml",
        )

        for required_path in required_paths:
            if not required_path.is_file():
                raise DeploymentError(
                    f"No existe el archivo requerido: {required_path}"
                )

    def preflight(self, state):
        self.run_compose(state, "config", "--quiet")
        self.run_compose(
            state,
            "pull",
            "migrate",
            "web",
            "backup",
            "backup-monitor",
            "restore",
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

    def create_backup(self, state):
        self.run_compose(
            state,
            "run",
            "--rm",
            "--no-deps",
            "backup",
        )
        self.run_compose(
            state,
            "run",
            "--rm",
            "--no-deps",
            "backup-monitor",
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

    def migrate(self, state):
        self.run_compose(
            state,
            "run",
            "--rm",
            "--no-deps",
            "migrate",
        )

    def start_application(self, state):
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
            "http://127.0.0.1:8080/healthz",
        )

    def rollback_application(self, previous_state):
        print(
            "El despliegue fallo; restaurando la imagen anterior "
            "sin revertir migraciones...",
            file=sys.stderr,
            flush=True,
        )
        self.run_compose(
            previous_state,
            "pull",
            "migrate",
            "web",
            "backup",
            "restore",
        )
        self.start_application(previous_state)

    def deploy(self, app_image, backup_image, skip_backup=False):
        target_state = {
            "app_image": validate_image_reference(
                app_image,
                "APP_IMAGE",
            ),
            "backup_image": validate_image_reference(
                backup_image,
                "BACKUP_IMAGE",
            ),
            "deployed_at": utc_now(),
        }
        self.verify_files()
        self.acquire_lock()

        try:
            current_state = self.load_state(self.current_state_path)
            self.preflight(target_state)
            self.validate_application(target_state)
            self.start_database(target_state)

            if not skip_backup:
                self.create_backup(target_state)

            try:
                self.migrate(target_state)
                self.start_application(target_state)
            except DeploymentError as deployment_error:
                if current_state:
                    try:
                        self.rollback_application(current_state)
                    except DeploymentError as rollback_error:
                        raise DeploymentError(
                            f"{deployment_error} El rollback automatico "
                            f"tambien fallo: {rollback_error}"
                        ) from rollback_error

                raise

            if current_state:
                self.write_state(
                    self.previous_state_path,
                    current_state,
                )

            self.write_state(self.current_state_path, target_state)
            return {
                "status": "deployed",
                **target_state,
            }
        finally:
            self.release_lock()

    def rollback(self, skip_backup=False):
        self.verify_files()
        self.acquire_lock()

        try:
            current_state = self.load_state(
                self.current_state_path,
                required=True,
            )
            previous_state = self.load_state(
                self.previous_state_path,
                required=True,
            )
            self.preflight(previous_state)
            self.start_database(previous_state)

            if not skip_backup:
                self.create_backup(previous_state)

            self.start_application(previous_state)
            rollback_state = {
                **previous_state,
                "deployed_at": utc_now(),
                "rollback_from": current_state["app_image"],
            }
            self.write_state(
                self.previous_state_path,
                current_state,
            )
            self.write_state(
                self.current_state_path,
                rollback_state,
            )
            return {
                "status": "rolled_back",
                **rollback_state,
            }
        finally:
            self.release_lock()


def build_parser():
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Despliega o revierte imagenes productivas por digest.",
    )
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
        "--wait-timeout",
        type=int,
        default=180,
    )
    parser.add_argument(
        "--skip-backup",
        action="store_true",
        help="Omite el backup previo; solo para recuperacion controlada.",
    )

    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument(
        "--deploy",
        action="store_true",
    )
    action.add_argument(
        "--rollback",
        action="store_true",
    )
    parser.add_argument(
        "--app-image",
        default=os.environ.get("APP_IMAGE", ""),
    )
    parser.add_argument(
        "--backup-image",
        default=os.environ.get("BACKUP_IMAGE", ""),
    )
    return parser


def main():
    arguments = build_parser().parse_args()

    if arguments.wait_timeout < 1:
        print(
            json.dumps(
                {
                    "status": "configuration_error",
                    "error": "--wait-timeout debe ser mayor o igual a 1.",
                }
            ),
            file=sys.stderr,
        )
        return 2

    controller = DeploymentController(
        project_root=arguments.project_root,
        env_file=arguments.env_file,
        state_directory=arguments.state_dir,
        wait_timeout=arguments.wait_timeout,
    )

    try:
        if arguments.deploy:
            if not arguments.app_image or not arguments.backup_image:
                raise DeploymentError(
                    "--deploy requiere --app-image y --backup-image."
                )

            result = controller.deploy(
                app_image=arguments.app_image,
                backup_image=arguments.backup_image,
                skip_backup=arguments.skip_backup,
            )
        else:
            result = controller.rollback(
                skip_backup=arguments.skip_backup,
            )
    except DeploymentError as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error": str(exc),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
