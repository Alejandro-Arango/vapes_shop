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


def validate_checkout_script(checkout_text):
    required_fragments = (
        "executor: 'per-vu-iterations'",
        "http.expectedStatuses(200, 400)",
        "checkout_successes",
        "checkout_rejections",
        "checkout_replays",
        "checkout_unexpected",
        "'Idempotency-Key': buyer.idempotency_key",
        "'X-CSRFToken': buyer.csrf_token",
        "/api/orders/checkout/",
        "checkout-summary.json",
    )

    return [
        f"performance/checkout.js no contiene {fragment}"
        for fragment in required_fragments
        if fragment not in checkout_text
    ]


def validate_checkout_fixture(fixture_text):
    required_fragments = (
        "CHECKOUT_LOAD_TEST_ENABLED",
        "performance",
        "Client(enforce_csrf_checks=True)",
        "client.force_login(user)",
        "session[\"cart\"]",
        "order_count_matches_initial_stock",
        "product_stock_is_zero",
        "idempotency_replays_match_orders",
        "movement_quantity_matches_stock",
    )

    return [
        f"performance/checkout_fixture.py no contiene {fragment}"
        for fragment in required_fragments
        if fragment not in fixture_text
    ]


def validate_coupon_script(coupon_text):
    required_fragments = (
        "executor: 'per-vu-iterations'",
        "http.expectedStatuses(200, 400)",
        "coupon_successes",
        "coupon_rejections",
        "coupon_replays",
        "coupon_unexpected",
        "body.coupon_code === fixture.coupon_code",
        "body.coupon_invalid === true",
        "/api/orders/checkout/",
        "coupon-summary.json",
    )

    return [
        f"performance/coupon.js no contiene {fragment}"
        for fragment in required_fragments
        if fragment not in coupon_text
    ]


def validate_coupon_fixture(fixture_text):
    required_fragments = (
        "CHECKOUT_LOAD_TEST_ENABLED",
        "performance",
        "session[\"coupon_code\"]",
        "max_uses=max_uses",
        "coupon_usage_matches_limit",
        "order_count_matches_coupon_limit",
        "remaining_stock_matches_rejections",
        "total_discount_matches_limit",
    )

    return [
        f"performance/coupon_fixture.py no contiene {fragment}"
        for fragment in required_fragments
        if fragment not in fixture_text
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

    required_fragments = (
        "image: mysql:8.4.10",
        "name: Probar checkout concurrente",
        "checkout_fixture.py",
        "verify",
        "checkout-invariants.json",
        "coupon_fixture.py",
        "run /scripts/coupon.js",
        "coupon-invariants.json",
        "rm -f performance-runtime/checkout-fixture.json",
        "rm -f performance-runtime/coupon-fixture.json",
    )

    for fragment in required_fragments:
        if fragment not in workflow_text:
            findings.append(
                f"performance.yml no contiene {fragment}"
            )

    return findings


def find_capacity_findings(project_root):
    project_root = Path(project_root)
    paths = {
        "compose": project_root / "compose.yaml",
        "local_env": project_root / "compose.env.example",
        "production_env": project_root / "compose.production.env.example",
        "load": project_root / "performance" / "catalog.js",
        "checkout": project_root / "performance" / "checkout.js",
        "checkout_fixture": (
            project_root / "performance" / "checkout_fixture.py"
        ),
        "coupon": project_root / "performance" / "coupon.js",
        "coupon_fixture": (
            project_root / "performance" / "coupon_fixture.py"
        ),
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
        validate_checkout_script(
            paths["checkout"].read_text(encoding="utf-8")
        )
    )
    findings.extend(
        validate_checkout_fixture(
            paths["checkout_fixture"].read_text(encoding="utf-8")
        )
    )
    findings.extend(
        validate_coupon_script(
            paths["coupon"].read_text(encoding="utf-8")
        )
    )
    findings.extend(
        validate_coupon_fixture(
            paths["coupon_fixture"].read_text(encoding="utf-8")
        )
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
