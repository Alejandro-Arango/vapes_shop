#!/usr/bin/env python3
"""Audita si un host Linux cumple el contrato operativo de produccion."""

import argparse
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


SUPPORTED_UBUNTU_RELEASES = {"22.04", "24.04"}
SAFE_BIND_ADDRESSES = {"127.0.0.1"}
ENV_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
OPERATIONAL_UNITS = (
    "vapes-shop-backup.service",
    "vapes-shop-backup.timer",
    "vapes-shop-production-monitor.service",
    "vapes-shop-production-monitor.timer",
    "vapes-shop-recovery-drill.service",
    "vapes-shop-recovery-drill.timer",
)
PRODUCTION_TIMERS = (
    "vapes-shop-backup.timer",
    "vapes-shop-production-monitor.timer",
    "vapes-shop-recovery-drill.timer",
)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00",
        "Z",
    )


def read_os_release(path=Path("/etc/os-release")):
    values = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip('"')
    return values


def validate_ubuntu_release(values):
    findings = []
    if values.get("ID") != "ubuntu":
        findings.append("El host no ejecuta Ubuntu.")
    if values.get("VERSION_ID") not in SUPPORTED_UBUNTU_RELEASES:
        findings.append(
            "Version de Ubuntu no soportada: "
            f"{values.get('VERSION_ID', 'desconocida')}."
        )
    if not values.get("VERSION_CODENAME"):
        findings.append("Ubuntu no informa VERSION_CODENAME.")
    return findings


def parse_env_file(path):
    values = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Linea {line_number} sin asignacion.")
        key, value = line.split("=", 1)
        if not ENV_KEY_PATTERN.fullmatch(key):
            raise ValueError(f"Clave invalida en linea {line_number}: {key}")
        values[key] = value.strip().strip('"').strip("'")
    return values


def validate_production_environment(values, app_root):
    findings = []
    if values.get("APP_BIND_ADDRESS") not in SAFE_BIND_ADDRESSES:
        findings.append(
            "APP_BIND_ADDRESS debe limitar el proxy a loopback."
        )

    expected_backup_root = str(app_root / "backups")
    if values.get("BACKUP_PATH") != expected_backup_root:
        findings.append(
            f"BACKUP_PATH debe ser {expected_backup_root}."
        )

    if values.get("EXTERNAL_BACKUP_ENABLED", "").lower() != "true":
        findings.append("EXTERNAL_BACKUP_ENABLED debe ser true.")
    if values.get("BACKUP_REQUIRE_EXTERNAL", "").lower() != "true":
        findings.append("BACKUP_REQUIRE_EXTERNAL debe ser true.")
    return findings


def validate_path(path, expected_uid, allowed_mode, label):
    findings = []
    try:
        path_stat = path.lstat()
    except OSError as exc:
        return [f"{label} no es accesible: {exc.__class__.__name__}."]

    if stat.S_ISLNK(path_stat.st_mode):
        findings.append(f"{label} no puede ser un enlace simbolico.")
    if expected_uid is not None and path_stat.st_uid != expected_uid:
        findings.append(f"{label} tiene propietario incorrecto.")

    actual_mode = stat.S_IMODE(path_stat.st_mode)
    if actual_mode & ~allowed_mode:
        findings.append(
            f"{label} tiene permisos {actual_mode:04o}; "
            f"maximo permitido {allowed_mode:04o}."
        )
    return findings


class CommandRunner:
    def run(self, command):
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, exc.__class__.__name__

        output = (completed.stdout or completed.stderr).strip()
        return completed.returncode == 0, output


def command_check(runner, name, command, predicate=None):
    success, output = runner.run(command)
    if success and (predicate is None or predicate(output)):
        return {
            "name": name,
            "status": "ok",
            "detail": output[:500],
        }
    return {
        "name": name,
        "status": "critical",
        "detail": output[:500] or "comando fallido",
    }


def firewall_default_deny_enabled(output):
    normalized_output = output.lower()
    active_markers = (
        "status: active",
        "estado: activo",
    )
    deny_incoming_markers = (
        "deny (incoming)",
        "deny (entrante)",
        "denegar (entrante)",
    )

    return any(
        marker in normalized_output for marker in active_markers
    ) and any(
        marker in normalized_output for marker in deny_incoming_markers
    )


def resolve_identity(user_name):
    import grp
    import pwd

    user = pwd.getpwnam(user_name)
    groups = {
        entry.gr_name
        for entry in grp.getgrall()
        if user_name in entry.gr_mem
    }
    groups.add(grp.getgrgid(user.pw_gid).gr_name)
    return user.pw_uid, groups


def audit_host(
    app_root,
    app_user="vapes-shop",
    mode="bootstrap",
    runner=None,
):
    runner = runner or CommandRunner()
    app_root = Path(os.path.abspath(os.fspath(app_root)))
    findings = []
    checks = []

    if platform.system() != "Linux":
        findings.append("La auditoria productiva requiere Linux.")

    try:
        findings.extend(validate_ubuntu_release(read_os_release()))
    except OSError as exc:
        findings.append(
            f"No fue posible leer /etc/os-release: {exc.__class__.__name__}."
        )

    try:
        app_uid, groups = resolve_identity(app_user)
        if "docker" not in groups:
            findings.append(f"{app_user} no pertenece al grupo docker.")
    except (ImportError, KeyError, OSError) as exc:
        app_uid = None
        findings.append(
            f"No fue posible resolver el usuario {app_user}: "
            f"{exc.__class__.__name__}."
        )

    for executable in (
        "docker",
        "gh",
        "git",
        "python3",
        "systemctl",
        "ufw",
    ):
        if shutil.which(executable) is None:
            findings.append(f"No existe el ejecutable requerido: {executable}.")

    checks.extend(
        (
            command_check(
                runner,
                "docker_engine",
                ["docker", "version", "--format", "{{.Server.Version}}"],
                bool,
            ),
            command_check(
                runner,
                "docker_compose",
                ["docker", "compose", "version", "--short"],
                bool,
            ),
            command_check(
                runner,
                "github_cli",
                ["gh", "version"],
                lambda value: "gh version 2.95.0" in value,
            ),
            command_check(
                runner,
                "docker_active",
                ["systemctl", "is-active", "docker.service"],
                lambda value: value == "active",
            ),
            command_check(
                runner,
                "docker_enabled",
                ["systemctl", "is-enabled", "docker.service"],
                lambda value: value == "enabled",
            ),
            command_check(
                runner,
                "security_update_lists",
                ["systemctl", "is-enabled", "apt-daily.timer"],
                lambda value: value == "enabled",
            ),
            command_check(
                runner,
                "security_update_lists_active",
                ["systemctl", "is-active", "apt-daily.timer"],
                lambda value: value == "active",
            ),
            command_check(
                runner,
                "security_upgrades",
                ["systemctl", "is-enabled", "apt-daily-upgrade.timer"],
                lambda value: value == "enabled",
            ),
            command_check(
                runner,
                "security_upgrades_active",
                ["systemctl", "is-active", "apt-daily-upgrade.timer"],
                lambda value: value == "active",
            ),
            command_check(
                runner,
                "firewall",
                ["ufw", "status", "verbose"],
                firewall_default_deny_enabled,
            ),
        )
    )

    path_contracts = (
        (app_root, 0o750, "directorio de aplicacion"),
        (app_root / "backups", 0o750, "directorio de backups"),
        (
            app_root / "external-backups",
            0o750,
            "directorio de backups externos",
        ),
        (app_root / "secrets", 0o700, "directorio de secretos"),
        (app_root / ".deploy", 0o750, "estado de despliegue"),
        (Path("/var/lib/vapes-shop"), 0o750, "estado operativo"),
    )
    for path, allowed_mode, label in path_contracts:
        findings.extend(
            validate_path(path, app_uid, allowed_mode, label)
        )

    findings.extend(
        validate_path(
            Path("/etc/vapes-shop"),
            0,
            0o750,
            "configuracion operativa",
        )
    )
    findings.extend(
        validate_path(
            Path(
                "/etc/vapes-shop/"
                "backup-operations.env.example"
            ),
            0,
            0o640,
            "ejemplo de configuracion operativa",
        )
    )
    findings.extend(
        validate_path(
            Path(
                "/etc/vapes-shop/"
                "production-monitor.env.example"
            ),
            0,
            0o640,
            "ejemplo de monitoreo productivo",
        )
    )
    for unit in OPERATIONAL_UNITS:
        findings.extend(
            validate_path(
                Path("/etc/systemd/system") / unit,
                0,
                0o644,
                f"unidad {unit}",
            )
        )

    unattended_path = Path(
        "/etc/apt/apt.conf.d/52vapes-shop-unattended-upgrades"
    )
    try:
        unattended_text = unattended_path.read_text(encoding="utf-8")
        if 'Automatic-Reboot "false"' not in unattended_text:
            findings.append(
                "Las actualizaciones pueden reiniciar el host automaticamente."
            )
    except OSError as exc:
        findings.append(
            "No fue posible validar la politica de reinicio: "
            f"{exc.__class__.__name__}."
        )

    if mode == "production":
        env_path = app_root / "compose.production.env"
        findings.extend(
            validate_path(
                env_path,
                app_uid,
                0o600,
                "entorno productivo",
            )
        )
        try:
            findings.extend(
                validate_production_environment(
                    parse_env_file(env_path),
                    app_root,
                )
            )
        except (OSError, ValueError) as exc:
            findings.append(f"Entorno productivo invalido: {exc}")

        findings.extend(
            validate_path(
                app_root / ".deploy" / "current.json",
                app_uid,
                0o600,
                "estado productivo actual",
            )
        )
        findings.extend(
            validate_path(
                Path("/etc/vapes-shop/production-monitor.env"),
                0,
                0o640,
                "entorno de monitoreo productivo",
            )
        )
        for timer in PRODUCTION_TIMERS:
            checks.append(
                command_check(
                    runner,
                    timer,
                    ["systemctl", "is-enabled", timer],
                    lambda value: value == "enabled",
                )
            )
            checks.append(
                command_check(
                    runner,
                    f"{timer}:active",
                    ["systemctl", "is-active", timer],
                    lambda value: value == "active",
                )
            )
        checks.extend(
            (
                command_check(
                    runner,
                    "source_checkout",
                    [
                        "git",
                        "-C",
                        str(app_root),
                        "rev-parse",
                        "--is-inside-work-tree",
                    ],
                    lambda value: value == "true",
                ),
                command_check(
                    runner,
                    "source_clean",
                    [
                        "git",
                        "-C",
                        str(app_root),
                        "status",
                        "--porcelain=v1",
                        "--untracked-files=no",
                    ],
                    lambda value: not value,
                ),
            )
        )

    findings.extend(
        f"{check['name']}: {check['detail']}"
        for check in checks
        if check["status"] != "ok"
    )
    return {
        "event": "host_readiness",
        "status": "healthy" if not findings else "critical",
        "mode": mode,
        "checked_at": utc_now(),
        "app_root": str(app_root),
        "checks": checks,
        "findings": findings,
    }


def write_report(path, report):
    output_path = Path(os.path.abspath(os.fspath(path)))
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")

    if (
        output_path.is_symlink()
        or output_path.parent.is_symlink()
        or temporary_path.is_symlink()
    ):
        raise ValueError("El reporte no puede reemplazar un enlace simbolico.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary_path, 0o600)
    os.replace(temporary_path, output_path)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Audita la preparacion de un host Ubuntu productivo.",
    )
    parser.add_argument("--app-root", default="/srv/vapes-shop")
    parser.add_argument("--app-user", default="vapes-shop")
    parser.add_argument(
        "--mode",
        choices=("bootstrap", "production"),
        default="bootstrap",
    )
    parser.add_argument("--output")
    return parser


def main():
    arguments = build_parser().parse_args()
    report = audit_host(
        app_root=arguments.app_root,
        app_user=arguments.app_user,
        mode=arguments.mode,
    )
    if arguments.output:
        write_report(arguments.output, report)
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    return 0 if report["status"] == "healthy" else 1


if __name__ == "__main__":
    raise SystemExit(main())
