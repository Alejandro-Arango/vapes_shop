#!/usr/bin/env python3
"""
Valida que Compose, k6 y CI conserven la politica minima de capacidad.
No requiere dependencias externas ni ejecuta carga contra un entorno real.
"""

import re
import sys
from pathlib import Path


RESOURCE_POLICY = {
    "db": ("DB_MEMORY_LIMIT", "DB_CPU_LIMIT", "pids_limit"),
    "migrate": ("MIGRATE_MEMORY_LIMIT", "MIGRATE_CPU_LIMIT", "pids_limit"),
    "web": ("WEB_MEMORY_LIMIT", "WEB_CPU_LIMIT", "pids_limit"),
    "proxy": ("PROXY_MEMORY_LIMIT", "PROXY_CPU_LIMIT", "pids_limit"),
    "backup": ("BACKUP_MEMORY_LIMIT", "BACKUP_CPU_LIMIT", "pids_limit"),
    "restore": ("RESTORE_MEMORY_LIMIT", "RESTORE_CPU_LIMIT", "pids_limit"),
}
ENV_RESOURCE_KEYS = tuple(
    value
    for values in RESOURCE_POLICY.values()
    for value in values
    if value != "pids_limit"
)
K6_IMAGE_PATTERN = re.compile(
    r"grafana/k6:2\.0\.0@sha256:[0-9a-f]{64}"
)


def extract_service_blocks(compose_text):
    services = {}
    current_name = None
    current_lines = []
    inside_services = False

    for line in compose_text.splitlines():
        if line == "services:":
            inside_services = True
            continue

        if not inside_services:
            continue

        if line and not line.startswith(" "):
            break

        match = re.fullmatch(r"  ([a-zA-Z0-9_-]+):", line)

        if match:
            if current_name:
                services[current_name] = "\n".join(current_lines)

            current_name = match.group(1)
            current_lines = []
            continue

        if current_name:
            current_lines.append(line)

    if current_name:
        services[current_name] = "\n".join(current_lines)

    return services


def validate_compose(compose_text):
    findings = []
    services = extract_service_blocks(compose_text)

    for service_name, required_values in RESOURCE_POLICY.items():
        block = services.get(service_name)

        if block is None:
            findings.append(f"falta el servicio {service_name} en Compose")
            continue

        if "mem_limit:" not in block:
            findings.append(f"{service_name} no define mem_limit")

        if "cpus:" not in block:
            findings.append(f"{service_name} no define cpus")

        for required_value in required_values:
            if required_value not in block:
                findings.append(
                    f"{service_name} no aplica {required_value}"
                )

    return findings


def parse_env_keys(env_text):
    keys = set()

    for raw_line in env_text.splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        keys.add(line.split("=", 1)[0].strip())

    return keys


def validate_env(env_text, env_name):
    keys = parse_env_keys(env_text)

    return [
        f"{env_name} no define {key}"
        for key in ENV_RESOURCE_KEYS
        if key not in keys
    ]


def validate_load_script(load_text):
    required_fragments = (
        "smoke:",
        "baseline:",
        "http_req_failed: ['rate<0.01']",
        "checks: ['rate>0.99']",
        "http_req_duration{endpoint:catalog}",
        "http_req_duration{endpoint:home}",
        "http_req_duration{endpoint:health}",
        "/api/products/?page=1&page_size=24",
        "performance-summary.json",
    )

    return [
        f"performance/catalog.js no contiene {fragment}"
        for fragment in required_fragments
        if fragment not in load_text
    ]


def validate_workflow(workflow_text):
    findings = []

    if not K6_IMAGE_PATTERN.search(workflow_text):
        findings.append("performance.yml no fija k6 2.0.0 por digest")

    for profile_name in ("smoke", "baseline"):
        if profile_name not in workflow_text:
            findings.append(
                f"performance.yml no selecciona el perfil {profile_name}"
            )

    return findings


def find_capacity_findings(project_root):
    project_root = Path(project_root)
    paths = {
        "compose": project_root / "compose.yaml",
        "local_env": project_root / "compose.env.example",
        "production_env": project_root / "compose.production.env.example",
        "load": project_root / "performance" / "catalog.js",
        "workflow": project_root / ".github" / "workflows" / "performance.yml",
    }
    missing_paths = [
        str(path.relative_to(project_root))
        for path in paths.values()
        if not path.is_file()
    ]

    if missing_paths:
        return [f"falta el archivo {path}" for path in missing_paths]

    findings = []
    findings.extend(
        validate_compose(paths["compose"].read_text(encoding="utf-8"))
    )
    findings.extend(
        validate_env(
            paths["local_env"].read_text(encoding="utf-8"),
            "compose.env.example",
        )
    )
    findings.extend(
        validate_env(
            paths["production_env"].read_text(encoding="utf-8"),
            "compose.production.env.example",
        )
    )
    findings.extend(
        validate_load_script(paths["load"].read_text(encoding="utf-8"))
    )
    findings.extend(
        validate_workflow(paths["workflow"].read_text(encoding="utf-8"))
    )
    return findings


def main():
    project_root = Path(__file__).resolve().parents[1]
    findings = find_capacity_findings(project_root)

    if findings:
        print("La politica de capacidad tiene errores:", file=sys.stderr)

        for finding in findings:
            print(f"- {finding}", file=sys.stderr)

        return 1

    print("La politica de capacidad esta completa y fijada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
