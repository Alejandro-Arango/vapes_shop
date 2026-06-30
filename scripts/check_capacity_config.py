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
    "backup-monitor": (
        "BACKUP_MONITOR_MEMORY_LIMIT",
        "BACKUP_MONITOR_CPU_LIMIT",
        "pids_limit",
    ),
    "external-backup": (
        "EXTERNAL_BACKUP_MEMORY_LIMIT",
        "EXTERNAL_BACKUP_CPU_LIMIT",
        "pids_limit",
    ),
    "external-recovery": (
        "EXTERNAL_BACKUP_MEMORY_LIMIT",
        "EXTERNAL_BACKUP_CPU_LIMIT",
        "pids_limit",
    ),
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


def validate_cancel_script(cancel_text):
    required_fragments = (
        "executor: 'per-vu-iterations'",
        "http.expectedStatuses(200, 400)",
        "cancel_successes",
        "cancel_rejections",
        "cancel_unexpected",
        "/api/orders/cancel/${fixture.order_id}/",
        "body.error.toLowerCase().includes('cerrada')",
        "cancel-summary.json",
    )

    return [
        f"performance/cancel.js no contiene {fragment}"
        for fragment in required_fragments
        if fragment not in cancel_text
    ]


def validate_cancel_fixture(fixture_text):
    required_fragments = (
        "CHECKOUT_LOAD_TEST_ENABLED",
        "performance",
        "movement_type=\"checkout\"",
        "cancel_history_created_once",
        "product_stock_restored_once",
        "restore_movement_created_once",
        "success_event_created_once",
    )

    return [
        f"performance/cancel_fixture.py no contiene {fragment}"
        for fragment in required_fragments
        if fragment not in fixture_text
    ]


def validate_image_pipeline(pipeline_text):
    required_fragments = (
        "IMAGE_PIPELINE_TEST_ENABLED",
        "ThreadPoolExecutor",
        "sanitize_product_image",
        "product_image_upload_to",
        "Se detectaron colisiones de nombres.",
        "La normalizacion conservo datos no seguros.",
        "image.format != \"PNG\"",
    )

    return [
        f"performance/image_pipeline.py no contiene {fragment}"
        for fragment in required_fragments
        if fragment not in pipeline_text
    ]


def validate_media_proxy(nginx_text):
    required_fragments = (
        "location /media/",
        "add_header X-Content-Type-Options nosniff always;",
        "add_header Cross-Origin-Resource-Policy same-origin always;",
        "add_header Content-Security-Policy "
        "\"default-src 'none'; sandbox\" always;",
    )

    return [
        f"docker/nginx.conf no contiene {fragment}"
        for fragment in required_fragments
        if fragment not in nginx_text
    ]


def validate_recovery_script(recovery_text):
    required_fragments = (
        "executor: 'constant-arrival-rate'",
        "pressure_accepted",
        "pressure_shed",
        "pressure_unexpected",
        "http.expectedStatuses(200, 429, 502, 503, 504)",
        "recovery-pressure-summary.json",
    )

    return [
        f"performance/recovery.js no contiene {fragment}"
        for fragment in required_fragments
        if fragment not in recovery_text
    ]


def validate_recovery_verifier(verifier_text):
    required_fragments = (
        "consecutive_successes",
        "status\": \"recovered\"",
        "status\": \"timeout\"",
        "check_readiness",
        "elapsed_seconds",
        "output_path.is_symlink()",
        "output_path.parent.is_symlink()",
        "temporary_path.is_symlink()",
        "El reporte de recuperacion no admite enlaces simbolicos",
        "os.chmod(temporary_path, 0o600)",
        "os.replace(temporary_path, output_path)",
    )

    return [
        f"scripts/verify_recovery.py no contiene {fragment}"
        for fragment in required_fragments
        if fragment not in verifier_text
    ]


def validate_dependency_outage_verifier(verifier_text):
    required_fragments = (
        "check_liveness",
        "check_database_outage",
        "database\": \"unavailable\"",
        "cache\": \"not_checked\"",
        "status\": \"degraded_as_expected\"",
        "consecutive_successes",
        "output_path.is_symlink()",
        "output_path.parent.is_symlink()",
        "temporary_path.is_symlink()",
        "El reporte de dependencia no admite enlaces simbolicos",
        "os.chmod(temporary_path, 0o600)",
        "os.replace(temporary_path, output_path)",
    )

    return [
        f"scripts/verify_dependency_outage.py no contiene {fragment}"
        for fragment in required_fragments
        if fragment not in verifier_text
    ]


def validate_media_storage_verifier(verifier_text):
    required_fragments = (
        "MEDIA_STORAGE_TEST_ENABLED",
        "default_storage",
        "operational/.write-probe-",
        "unavailable_as_expected",
        "El archivo persistente no conserva su contenido.",
        "storage.delete(saved_name)",
        "output_path.is_symlink()",
        "output_path.parent.is_symlink()",
        "temporary_path.is_symlink()",
        "El reporte de almacenamiento media no admite enlaces simbolicos",
        "os.chmod(temporary_path, 0o600)",
        "os.replace(temporary_path, output_path)",
    )

    return [
        f"scripts/verify_media_storage.py no contiene {fragment}"
        for fragment in required_fragments
        if fragment not in verifier_text
    ]


def validate_backup_monitor(monitor_text):
    required_fragments = (
        "BACKUP_ID_PATTERN",
        "manifest.sha256",
        "sha256_file",
        "validate_database_archive",
        "validate_media_archive",
        "BACKUP_MAX_AGE_HOURS",
        "BACKUP_MIN_FREE_BYTES",
        "BACKUP_MIN_FREE_PERCENT",
        "BACKUP_MIN_FREE_COPIES",
        "status\": \"critical\"",
        "root.is_symlink()",
        "root.parent.is_symlink()",
        "BACKUP_ROOT no puede ser un enlace simbolico",
        "output_path.is_symlink()",
        "output_path.parent.is_symlink()",
        "temporary_path.is_symlink()",
        "El reporte de monitoreo de backups no admite enlaces simbolicos",
        "os.chmod(temporary_path, 0o600)",
        "os.replace(temporary_path, output_path)",
    )

    return [
        f"scripts/monitor_backups.py no contiene {fragment}"
        for fragment in required_fragments
        if fragment not in monitor_text
    ]


def validate_production_monitor(monitor_text):
    required_fragments = (
        "MAX_RESPONSE_BYTES",
        "NoRedirectHandler",
        "X-Request-ID",
        "status\": \"critical\"",
        "status\": \"configuration_error\"",
        "send_webhook",
        "MONITOR_REPORT_PATH",
        "report_error",
        "output_path.is_symlink()",
        "output_path.parent.is_symlink()",
        "temporary_path.is_symlink()",
        "El reporte de monitoreo productivo no admite enlaces simbolicos",
        "os.chmod(temporary_path, 0o600)",
        "os.replace(temporary_path, output_path)",
    )

    return [
        f"scripts/monitor_production.py no contiene {fragment}"
        for fragment in required_fragments
        if fragment not in monitor_text
    ]


def validate_production_monitor_schedule(
    monitor_service_text,
    monitor_timer_text,
    monitor_env_text,
    monitor_workflow_text,
    django_workflow_text,
    bootstrap_text,
    host_docs_text,
):
    required_fragments = (
        (
            monitor_service_text,
            "monitor_production.py --attempts 3 --retry-delay 10 --timeout 10",
            "vapes-shop-production-monitor.service",
        ),
        (
            monitor_service_text,
            "EnvironmentFile=/etc/vapes-shop/production-monitor.env",
            "vapes-shop-production-monitor.service",
        ),
        (
            monitor_service_text,
            "MONITOR_REPORT_PATH=/var/lib/vapes-shop/production-monitor.json",
            "vapes-shop-production-monitor.service",
        ),
        (
            monitor_service_text,
            "NoNewPrivileges=true",
            "vapes-shop-production-monitor.service",
        ),
        (
            monitor_service_text,
            "PrivateTmp=true",
            "vapes-shop-production-monitor.service",
        ),
        (
            monitor_service_text,
            "UMask=0077",
            "vapes-shop-production-monitor.service",
        ),
        (
            monitor_timer_text,
            "OnCalendar=*:0/15",
            "vapes-shop-production-monitor.timer",
        ),
        (
            monitor_timer_text,
            "Persistent=true",
            "vapes-shop-production-monitor.timer",
        ),
        (
            monitor_timer_text,
            "Unit=vapes-shop-production-monitor.service",
            "vapes-shop-production-monitor.timer",
        ),
        (
            monitor_env_text,
            "PRODUCTION_HEALTH_URL=",
            "production-monitor.env.example",
        ),
        (
            monitor_env_text,
            "MONITOR_WEBHOOK_URL=",
            "production-monitor.env.example",
        ),
        (
            monitor_env_text,
            "MONITOR_WEBHOOK_TOKEN=",
            "production-monitor.env.example",
        ),
        (
            monitor_workflow_text,
            "--output monitor-results/production-monitor.json",
            "production-monitor.yml",
        ),
        (
            monitor_workflow_text,
            "actions/upload-artifact@v4",
            "production-monitor.yml",
        ),
        (
            monitor_workflow_text,
            "production-monitor-report",
            "production-monitor.yml",
        ),
        (
            monitor_workflow_text,
            "if: always()",
            "production-monitor.yml",
        ),
        (
            django_workflow_text,
            "vapes-shop-production-monitor.service",
            "django-ci.yml",
        ),
        (
            django_workflow_text,
            "vapes-shop-production-monitor.timer",
            "django-ci.yml",
        ),
        (
            bootstrap_text,
            "production-monitor.env.example",
            "ubuntu-bootstrap.sh",
        ),
        (
            host_docs_text,
            "production-monitor.env",
            "HOST_PROVISIONING.md",
        ),
        (
            host_docs_text,
            "vapes-shop-production-monitor.timer",
            "HOST_PROVISIONING.md",
        ),
    )

    return [
        f"{label} no contiene {fragment}"
        for text, fragment, label in required_fragments
        if fragment not in text
    ]


def validate_codeowners(codeowners_text):
    required_fragments = (
        "* @Alejandro-Arango",
        "/.github/ @Alejandro-Arango",
        "/ops/ @Alejandro-Arango",
        "/ops/systemd/ @Alejandro-Arango",
        "/scripts/backup_operations.py @Alejandro-Arango",
        "/scripts/external_backup.py @Alejandro-Arango",
        "/scripts/monitor_backups.py @Alejandro-Arango",
        "/scripts/deploy_production.py @Alejandro-Arango",
        "/scripts/recover_production.py @Alejandro-Arango",
        "/scripts/release_manifest.py @Alejandro-Arango",
        "/scripts/fetch_release_manifest.py @Alejandro-Arango",
        "/scripts/check_host_readiness.py @Alejandro-Arango",
        "/scripts/monitor_production.py @Alejandro-Arango",
        "/scripts/check_capacity_config.py @Alejandro-Arango",
        "/scripts/check_secret_files.py @Alejandro-Arango",
        "/scripts/check_zap_rules.py @Alejandro-Arango",
        "/backend/mi_tienda/settings.py @Alejandro-Arango",
        (
            "/backend/store/management/commands/production_check.py "
            "@Alejandro-Arango"
        ),
    )

    return [
        f"CODEOWNERS no contiene {fragment}"
        for fragment in required_fragments
        if fragment not in codeowners_text
    ]


def workflow_job_has_timeout(workflow_text, job_name, timeout_minutes):
    marker = f"  {job_name}:\n"
    start = workflow_text.find(marker)

    if start == -1:
        return False

    remaining_text = workflow_text[start + len(marker):]
    next_job = re.search(r"\n  [A-Za-z0-9_-]+:\n", remaining_text)
    end = next_job.start() if next_job else len(remaining_text)
    job_block = remaining_text[:end]

    return f"    timeout-minutes: {timeout_minutes}\n" in job_block


def validate_security_workflow_timeouts(
    secret_scan_workflow_text,
    supply_chain_workflow_text,
):
    required_jobs = (
        (
            secret_scan_workflow_text,
            "secret-scan.yml",
            "gitleaks",
            15,
        ),
        (
            supply_chain_workflow_text,
            "supply-chain.yml",
            "python-dependencies",
            15,
        ),
        (
            supply_chain_workflow_text,
            "supply-chain.yml",
            "container-images",
            30,
        ),
    )

    return [
        f"{workflow_name} no limita {job_name} a {timeout_minutes} minutos"
        for workflow_text, workflow_name, job_name, timeout_minutes in required_jobs
        if not workflow_job_has_timeout(workflow_text, job_name, timeout_minutes)
    ]


def validate_django_workflow_timeouts(django_workflow_text):
    required_jobs = (
        ("validate", 20),
        ("container", 20),
        ("database_outage", 20),
        ("media_outage", 15),
        ("recovery", 30),
    )

    return [
        f"django-ci.yml no limita {job_name} a {timeout_minutes} minutos"
        for job_name, timeout_minutes in required_jobs
        if not workflow_job_has_timeout(
            django_workflow_text,
            job_name,
            timeout_minutes,
        )
    ]


def validate_publish_workflow_timeouts(publish_workflow_text):
    required_jobs = (
        ("validate", 30),
        ("publish", 45),
    )

    return [
        f"publish-images.yml no limita {job_name} a {timeout_minutes} minutos"
        for job_name, timeout_minutes in required_jobs
        if not workflow_job_has_timeout(
            publish_workflow_text,
            job_name,
            timeout_minutes,
        )
    ]


def validate_backup_monitor_config(
    compose_text,
    production_compose_text,
    local_env_text,
    production_env_text,
    django_workflow_text,
    deploy_text,
):
    findings = []
    monitor_keys = (
        "BACKUP_MAX_AGE_HOURS",
        "BACKUP_FUTURE_TOLERANCE_MINUTES",
        "BACKUP_MIN_DATABASE_BYTES",
        "BACKUP_MIN_MEDIA_BYTES",
        "BACKUP_MIN_FREE_BYTES",
        "BACKUP_MIN_FREE_PERCENT",
        "BACKUP_MIN_FREE_COPIES",
    )
    required_fragments = (
        (compose_text, "backup-monitor:", "compose.yaml"),
        (compose_text, "/monitor/monitor_backups.py", "compose.yaml"),
        (
            compose_text,
            "./scripts/monitor_backups.py:/monitor/monitor_backups.py:ro",
            "compose.yaml",
        ),
        (compose_text, "${BACKUP_PATH:-./backups}:/backups:ro", "compose.yaml"),
        (production_compose_text, "backup-monitor:", "compose.production.yaml"),
        (django_workflow_text, "python scripts/monitor_backups.py", "django-ci.yml"),
        (django_workflow_text, "backup-health.json", "django-ci.yml"),
        (deploy_text, '"backup-monitor"', "deploy_production.py"),
    )

    for text, fragment, label in required_fragments:
        if fragment not in text:
            findings.append(f"{label} no contiene {fragment}")

    for key in monitor_keys:
        if key not in compose_text:
            findings.append(f"compose.yaml no propaga {key}")

        if key not in parse_env_keys(local_env_text):
            findings.append(f"compose.env.example no define {key}")

        if key not in parse_env_keys(production_env_text):
            findings.append(f"compose.production.env.example no define {key}")

    return findings


def validate_external_backup_script(script_text):
    required_fragments = (
        "INIT-EXTERNAL-BACKUP",
        "RECOVER-LATEST-EXTERNAL-BACKUP",
        "RESTIC_REPOSITORY_FILE",
        "RESTIC_PASSWORD_FILE",
        "EXTERNAL_BACKUP_MIN_PASSWORD_LENGTH",
        "restic",
        "backup",
        "check",
        "restore",
        "forget",
        "compare_files",
        "verify_backup",
        "stored_and_restored",
        "recover_latest_external_backup",
        "backup_root.exists() and not backup_root.is_dir()",
        "restore_parent.exists() and not restore_parent.is_dir()",
        "BACKUP_ROOT debe estar vacio",
        "output_path.is_symlink()",
        "output_path.parent.is_symlink()",
        "temporary_path.is_symlink()",
        "El reporte de backup externo no admite enlaces simbolicos",
        "os.chmod(temporary_path, 0o600)",
        "os.replace(temporary_path, output_path)",
        '"status": "recovered"',
    )

    return [
        f"scripts/external_backup.py no contiene {fragment}"
        for fragment in required_fragments
        if fragment not in script_text
    ]


def validate_external_backup_config(
    backup_dockerfile_text,
    compose_text,
    production_compose_text,
    local_env_text,
    production_env_text,
    django_workflow_text,
    deploy_text,
):
    findings = []
    external_keys = (
        "EXTERNAL_BACKUP_ENABLED",
        "EXTERNAL_BACKUP_HOST",
        "EXTERNAL_BACKUP_CHECK_SUBSET",
        "EXTERNAL_BACKUP_KEEP_DAILY",
        "EXTERNAL_BACKUP_KEEP_WEEKLY",
        "EXTERNAL_BACKUP_KEEP_MONTHLY",
        "EXTERNAL_BACKUP_MIN_PASSWORD_LENGTH",
        "EXTERNAL_BACKUP_COMMAND_TIMEOUT",
        "EXTERNAL_BACKUP_LOCAL_PATH",
        "EXTERNAL_BACKUP_REPOSITORY_FILE",
        "EXTERNAL_BACKUP_PASSWORD_FILE",
        "EXTERNAL_BACKUP_ENV_FILE",
    )
    required_fragments = (
        (
            backup_dockerfile_text,
            "ARG RESTIC_VERSION=0.19.0",
            "docker/backup.Dockerfile",
        ),
        (
            backup_dockerfile_text,
            "13176fe6d89d4357947a2cd107218ab2873a5f9d8e1ac2d4cd1c8e07e6839c21",
            "docker/backup.Dockerfile",
        ),
        (
            backup_dockerfile_text,
            "e522ce6bf748d753fee8093e8ec59359972cf5b6bc65fc7c7cf38ae952351d91",
            "docker/backup.Dockerfile",
        ),
        (
            backup_dockerfile_text,
            "sha256sum --check --strict",
            "docker/backup.Dockerfile",
        ),
        (
            backup_dockerfile_text,
            "scripts/monitor_backups.py scripts/external_backup.py",
            "docker/backup.Dockerfile",
        ),
        (compose_text, "external-backup:", "compose.yaml"),
        (
            compose_text,
            "${BACKUP_PATH:-./backups}:/backups:ro",
            "compose.yaml",
        ),
        (
            compose_text,
            "/run/secrets/restic_repository:ro",
            "compose.yaml",
        ),
        (
            compose_text,
            "/run/secrets/restic_password:ro",
            "compose.yaml",
        ),
        (
            compose_text,
            "external_restore_check:/restore-check",
            "compose.yaml",
        ),
        (compose_text, "external-recovery:", "compose.yaml"),
        (
            production_compose_text,
            "external-backup:",
            "compose.production.yaml",
        ),
        (
            production_compose_text,
            "external-recovery:",
            "compose.production.yaml",
        ),
        (
            django_workflow_text,
            "--confirm INIT-EXTERNAL-BACKUP",
            "django-ci.yml",
        ),
        (
            django_workflow_text,
            "external-restore-verification.json",
            "django-ci.yml",
        ),
        (
            django_workflow_text,
            "external-recovery-materialized.json",
            "django-ci.yml",
        ),
        (
            django_workflow_text,
            "repositorio Restic contiene datos de prueba en texto plano",
            "django-ci.yml",
        ),
        (
            deploy_text,
            '"external-backup"',
            "deploy_production.py",
        ),
    )

    for text, fragment, label in required_fragments:
        if fragment not in text:
            findings.append(f"{label} no contiene {fragment}")

    for key in external_keys:
        if key not in compose_text:
            findings.append(f"compose.yaml no propaga {key}")

        if key not in parse_env_keys(local_env_text):
            findings.append(f"compose.env.example no define {key}")

        if key not in parse_env_keys(production_env_text):
            findings.append(f"compose.production.env.example no define {key}")

    if "EXTERNAL_BACKUP_ENABLED=true" not in production_env_text:
        findings.append(
            "compose.production.env.example no activa el backup externo"
        )

    return findings


def validate_disaster_recovery(
    recovery_text,
    external_backup_text,
    deploy_text,
    compose_text,
    production_compose_text,
    local_env_text,
    production_env_text,
    django_workflow_text,
    disaster_docs_text,
):
    findings = []
    recovery_fragments = (
        "ProductionRecoveryController",
        "RECOVER-PRODUCTION-FROM-EXTERNAL-BACKUP",
        "USE-MANUAL-RECOVERY-IMAGES",
        "--break-glass-confirm",
        "--break-glass-reason",
        '"source_mode": "verified-manifest"',
        '"source_mode": "manual-break-glass"',
        "validate_recovery_provenance",
        "new_recovery_attempt_id",
        "validate_recovery_attempt_id",
        '"recovery_attempt_id": recovery_attempt_id',
        "recovery-in-progress.json",
        "last-recovery-report.json",
        "write_recovery_journal",
        "remove_recovery_journal",
        "write_recovery_audit",
        "audit_persisted",
        "if audit_persisted:",
        "exc.recovery_report = failure_report",
        'getattr(exc, "recovery_report", None)',
        '"phase": phase',
        "exc.recovery_phase = phase",
        'report["recovery_phase"] = recovery_phase',
        "journal de recuperacion interrumpida",
        "state_directory_path.is_symlink()",
        "state_directory_path.parent.is_symlink()",
        "El directorio de estado de recuperacion no admite",
        "current_state_path.is_symlink()",
        "current_state_path.parent.is_symlink()",
        "recovery_journal_path.parent.is_symlink()",
        "last_recovery_report_path.parent.is_symlink()",
        "temporary_path.is_symlink()",
        "El reporte no puede reemplazar un enlace simbolico",
        "El estado productivo no admite enlaces simbolicos",
        "recovery_attempt_id debe contener 32 caracteres hexadecimales",
        "build_failure_report",
        "report = build_failure_report(exc, source, attempt_id)",
        "verified-manifest no admite un motivo break-glass",
        "manual-break-glass no admite identidad de manifiesto",
        "MIN_BREAK_GLASS_REASON_LENGTH",
        "MAX_BREAK_GLASS_REASON_LENGTH",
        "self.state_directory.with_name",
        "Ya existe estado productivo",
        '"ps",',
        '"--all",',
        '"volume",',
        "label=com.docker.compose.project=vapes-shop",
        'environment["COMPOSE_PROJECT_NAME"] = "vapes-shop"',
        "verify_source_checkout",
        "--is-inside-work-tree",
        "rev-parse",
        "--porcelain=v1",
        "--untracked-files=no",
        "no coincide con source_commit",
        "contiene cambios rastreados",
        "external-recovery",
        "RECOVER-LATEST-EXTERNAL-BACKUP",
        '"RESTORE_CREATE_SAFETY_BACKUP": "false"',
        "manage.py\", \"check\", \"--deploy",
        "manage.py\", \"production_check",
        "/healthz",
        "/api/products/",
        "RTO integral incumplido",
        "os.chmod(temporary_path, 0o600)",
        "alert_failure",
    )

    for fragment in recovery_fragments:
        if fragment not in recovery_text:
            findings.append(
                f"recover_production.py no contiene {fragment}"
            )

    if recovery_text.count("temporary_path.is_symlink()") < 4:
        findings.append(
            (
                "recover_production.py no contiene 4 validaciones "
                "temporary_path.is_symlink()"
            )
        )

    for fragment in (
        "recover_latest_external_backup",
        "BACKUP_ROOT debe estar vacio",
        "os.replace(restored_backup_directory, destination)",
        "latest_path.is_symlink()",
        "temporary_latest.is_symlink()",
        "El indice latest de backup externo no admite rutas",
    ):
        if fragment not in external_backup_text:
            findings.append(
                f"external_backup.py no contiene {fragment}"
            )

    for text, fragment, label in (
        (compose_text, "external-recovery:", "compose.yaml"),
        (
            compose_text,
            "${BACKUP_PATH:-./backups}:/backups",
            "compose.yaml",
        ),
        (
            production_compose_text,
            "external-recovery:",
            "compose.production.yaml",
        ),
        (
            django_workflow_text,
            "--confirm RECOVER-LATEST-EXTERNAL-BACKUP",
            "django-ci.yml",
        ),
        (
            django_workflow_text,
            "external-recovery-materialized.json",
            "django-ci.yml",
        ),
        (
            deploy_text,
            "X-Forwarded-Proto: https",
            "deploy_production.py",
        ),
        (
            disaster_docs_text,
            "RECOVER-PRODUCTION-FROM-EXTERNAL-BACKUP",
            "DISASTER_RECOVERY.md",
        ),
        (
            disaster_docs_text,
            "USE-MANUAL-RECOVERY-IMAGES",
            "DISASTER_RECOVERY.md",
        ),
        (
            disaster_docs_text,
            "manual-break-glass",
            "DISASTER_RECOVERY.md",
        ),
        (
            disaster_docs_text,
            "reportes de error",
            "DISASTER_RECOVERY.md",
        ),
        (
            disaster_docs_text,
            "recovery_attempt_id",
            "DISASTER_RECOVERY.md",
        ),
        (
            disaster_docs_text,
            "recovery-in-progress.json",
            "DISASTER_RECOVERY.md",
        ),
        (
            disaster_docs_text,
            "last-recovery-report.json",
            "DISASTER_RECOVERY.md",
        ),
    ):
        if fragment not in text:
            findings.append(f"{label} no contiene {fragment}")

    for label, env_text in (
        ("compose.env.example", local_env_text),
        ("compose.production.env.example", production_env_text),
    ):
        if "DISASTER_RECOVERY_RTO_SECONDS" not in parse_env_keys(env_text):
            findings.append(
                f"{label} no define DISASTER_RECOVERY_RTO_SECONDS"
            )

    return findings


def validate_release_manifest(
    manifest_text,
    fetch_text,
    recovery_text,
    publish_workflow_text,
    disaster_docs_text,
    bootstrap_text,
    readiness_text,
):
    findings = []
    manifest_fragments = (
        "vapes-shop/recovery-manifest/v1",
        "release_tag",
        "source_commit",
        "images.application",
        "images.operations",
        "recovery.rto_seconds",
        "recovery-manifest.sha256",
        "load_verified_manifest",
        "expected_repository",
        "expected_tag",
        "temporary_path.is_symlink()",
        "temporal simbolico",
        "os.chmod(temporary_path, 0o600)",
        "os.replace",
    )
    recovery_fragments = (
        "load_verified_manifest",
        "--release-manifest",
        "--manifest-checksum",
        "--expected-repository",
        "--expected-tag",
        "No combines un manifiesto con parametros break-glass",
    )
    fetch_fragments = (
        "gh",
        "release",
        "download",
        "attestation",
        "verify",
        "prepare_output_directory",
        "output_directory.exists() and not output_directory.is_dir()",
        "El directorio de salida debe estar vacio",
        "El destino debe ser un directorio regular",
        "validate_downloaded_assets",
        "load_verified_manifest",
        "cleanup_assets",
    )
    workflow_fragments = (
        "python scripts/release_manifest.py create",
        'git rev-parse "${RELEASE_TAG}^{commit}"',
        'test "$source_commit" = "$tag_commit"',
        "actions/attest@v4",
        "subject-path: recovery-manifest.json",
        'gh release upload "$RELEASE_TAG"',
        "recovery-manifest.sha256",
        "release-recovery-manifest",
    )
    docs_fragments = (
        "scripts/fetch_release_manifest.py",
        "--release-manifest",
        "git -C /srv/vapes-shop checkout",
        "HEAD` coincide con `source_commit",
    )
    bootstrap_fragments = (
        "GH_VERSION",
        'gh_${GH_VERSION}_linux_',
        "25d1e4729e8808c9ed3d613e96ebd3f3e44446f2d368c89d878a71a36ddb3d8c",
        "d41e0b3b6218e5741c8bb4db39b16e53a59e0e06299a8489bd38f623ef7ebaae",
        "sha256sum --check --strict",
        "install_github_cli",
    )
    readiness_fragments = (
        '"gh",',
        '"github_cli"',
        "gh version 2.95.0",
    )

    for text, fragments, label in (
        (manifest_text, manifest_fragments, "release_manifest.py"),
        (fetch_text, fetch_fragments, "fetch_release_manifest.py"),
        (recovery_text, recovery_fragments, "recover_production.py"),
        (
            publish_workflow_text,
            workflow_fragments,
            "publish-images.yml",
        ),
        (disaster_docs_text, docs_fragments, "DISASTER_RECOVERY.md"),
        (bootstrap_text, bootstrap_fragments, "ubuntu-bootstrap.sh"),
        (readiness_text, readiness_fragments, "check_host_readiness.py"),
    ):
        for fragment in fragments:
            if fragment not in text:
                findings.append(f"{label} no contiene {fragment}")

    if manifest_text.count("temporary_path.is_symlink()") < 2:
        findings.append(
            (
                "release_manifest.py debe validar temporales simbolicos "
                "en manifiesto y checksum"
            )
        )

    if manifest_text.count("path.exists() and path.is_dir()") < 2:
        findings.append(
            (
                "release_manifest.py debe rechazar destinos directorio "
                "en manifiesto y checksum"
            )
        )

    if "gh release upload \"$RELEASE_TAG\"" in publish_workflow_text and (
        "--clobber" in publish_workflow_text
    ):
        findings.append(
            "publish-images.yml no debe reemplazar manifiestos publicados"
        )

    return findings


def validate_backup_operations(script_text):
    required_fragments = (
        "BackupOperationsController",
        "self.state_directory.with_name",
        "backup-monitor",
        "external-backup",
        "verify-latest",
        "BACKUP_REQUIRE_EXTERNAL",
        "RPO incumplido",
        "RTO incumplido",
        "rpo_actual_hours",
        "rto_actual_seconds",
        "alert_failure",
        "state_directory_path.is_symlink()",
        "state_directory_path.parent.is_symlink()",
        "El directorio de estado de backups no admite",
        "output_path.is_symlink()",
        "output_path.parent.is_symlink()",
        "temporary_path.is_symlink()",
        "El reporte de backup no admite enlaces simbolicos",
        "os.chmod(temporary_path, 0o600)",
        "os.replace(temporary_path, output_path)",
    )

    return [
        f"scripts/backup_operations.py no contiene {fragment}"
        for fragment in required_fragments
        if fragment not in script_text
    ]


def validate_backup_schedule(
    local_env_text,
    production_env_text,
    django_workflow_text,
    backup_service_text,
    backup_timer_text,
    drill_service_text,
    drill_timer_text,
    schedule_env_text,
):
    findings = []
    schedule_keys = (
        "BACKUP_REQUIRE_EXTERNAL",
        "BACKUP_RPO_HOURS",
        "BACKUP_RTO_SECONDS",
        "BACKUP_OPERATION_TIMEOUT",
        "BACKUP_ALERT_TIMEOUT",
    )
    required_fragments = (
        (
            backup_service_text,
            "backup_operations.py cycle",
            "vapes-shop-backup.service",
        ),
        (
            backup_service_text,
            "StateDirectory=vapes-shop",
            "vapes-shop-backup.service",
        ),
        (
            backup_service_text,
            "StateDirectoryMode=0750",
            "vapes-shop-backup.service",
        ),
        (
            backup_service_text,
            "EnvironmentFile=-/etc/vapes-shop/backup-operations.env",
            "vapes-shop-backup.service",
        ),
        (
            backup_timer_text,
            "OnCalendar=*-*-* 02:15:00 America/Bogota",
            "vapes-shop-backup.timer",
        ),
        (
            backup_timer_text,
            "Persistent=true",
            "vapes-shop-backup.timer",
        ),
        (
            drill_service_text,
            "backup_operations.py drill",
            "vapes-shop-recovery-drill.service",
        ),
        (
            drill_service_text,
            "StateDirectoryMode=0750",
            "vapes-shop-recovery-drill.service",
        ),
        (
            drill_timer_text,
            "OnCalendar=Sun *-*-* 04:00:00 America/Bogota",
            "vapes-shop-recovery-drill.timer",
        ),
        (
            drill_timer_text,
            "Persistent=true",
            "vapes-shop-recovery-drill.timer",
        ),
        (
            django_workflow_text,
            "systemd-analyze verify",
            "django-ci.yml",
        ),
        (
            django_workflow_text,
            "rpo-rto-drill.json",
            "django-ci.yml",
        ),
    )

    for text, fragment, label in required_fragments:
        if fragment not in text:
            findings.append(f"{label} no contiene {fragment}")

    for key in schedule_keys:
        if key not in parse_env_keys(local_env_text):
            findings.append(f"compose.env.example no define {key}")

        if key not in parse_env_keys(production_env_text):
            findings.append(f"compose.production.env.example no define {key}")

        if key not in parse_env_keys(schedule_env_text):
            findings.append(
                f"backup-operations.env.example no define {key}"
            )

    if "BACKUP_REQUIRE_EXTERNAL=true" not in production_env_text:
        findings.append(
            "compose.production.env.example no exige backup externo"
        )

    return findings


def validate_host_provisioning(
    bootstrap_text,
    readiness_text,
    deploy_text,
    compose_text,
    local_env_text,
    production_env_text,
    django_workflow_text,
):
    findings = []
    bootstrap_fragments = (
        "set -Eeuo pipefail",
        "https://download.docker.com/linux/ubuntu",
        "docker-compose-plugin",
        "unattended-upgrades",
        'Unattended-Upgrade::Automatic-Reboot "false"',
        "ufw default deny incoming",
        "ufw --force enable",
        "useradd",
        "--shell /usr/sbin/nologin",
        "usermod --append --groups docker",
        "vapes-shop-production-monitor.service",
        "production-monitor.env.example",
        "systemctl daemon-reload",
    )
    readiness_fragments = (
        "SUPPORTED_UBUNTU_RELEASES",
        "SAFE_BIND_ADDRESSES",
        "OPERATIONAL_UNITS",
        "PRODUCTION_TIMERS",
        "APP_BIND_ADDRESS debe limitar el proxy a loopback",
        "EXTERNAL_BACKUP_ENABLED debe ser true",
        "BACKUP_REQUIRE_EXTERNAL debe ser true",
        "apt-daily-upgrade.timer",
        "vapes-shop-backup.timer",
        "vapes-shop-production-monitor.timer",
        "vapes-shop-recovery-drill.timer",
        "production-monitor.env.example",
        "production-monitor.env",
        "os.replace(temporary_path, output_path)",
        "output_path.is_symlink()",
        "temporary_path.is_symlink()",
        '"source_checkout"',
        '"source_clean"',
        '"--untracked-files=no"',
    )

    for fragment in bootstrap_fragments:
        if fragment not in bootstrap_text:
            findings.append(
                f"ubuntu-bootstrap.sh no contiene {fragment}"
            )

    if "sshd_config" in bootstrap_text:
        findings.append(
            "ubuntu-bootstrap.sh no debe modificar sshd_config"
        )

    for fragment in readiness_fragments:
        if fragment not in readiness_text:
            findings.append(
                f"check_host_readiness.py no contiene {fragment}"
            )

    for fragment in (
        "os.chmod(temporary_path, 0o600)",
        "state_directory_path.is_symlink()",
        "state_directory_path.parent.is_symlink()",
        "El directorio de estado de despliegue no admite",
        "path.is_symlink()",
        "path.parent.is_symlink()",
        "temporary_path.is_symlink()",
        "El estado de despliegue no admite enlaces simbolicos",
    ):
        if fragment not in deploy_text:
            findings.append(
                "deploy_production.py no restringe los archivos de estado"
            )

    if "${APP_BIND_ADDRESS:-0.0.0.0}:${APP_PORT:-8080}:8080" not in (
        compose_text
    ):
        findings.append("compose.yaml no permite limitar APP_BIND_ADDRESS")

    if "APP_BIND_ADDRESS=0.0.0.0" not in local_env_text:
        findings.append(
            "compose.env.example no conserva acceso local por APP_BIND_ADDRESS"
        )

    if "APP_BIND_ADDRESS=127.0.0.1" not in production_env_text:
        findings.append(
            "compose.production.env.example no limita APP_BIND_ADDRESS"
        )

    for fragment in (
        "bash -n ops/provision/ubuntu-bootstrap.sh",
        "python scripts/check_host_readiness.py --help",
    ):
        if fragment not in django_workflow_text:
            findings.append(f"django-ci.yml no contiene {fragment}")

    return findings


def validate_resilience_config(
    start_text,
    nginx_text,
    compose_text,
    local_env_text,
    production_env_text,
):
    required_gunicorn_keys = (
        "GUNICORN_BACKLOG",
        "GUNICORN_GRACEFUL_TIMEOUT",
        "GUNICORN_KEEP_ALIVE",
        "GUNICORN_MAX_REQUESTS",
        "GUNICORN_MAX_REQUESTS_JITTER",
    )
    findings = []

    if '--backlog "${GUNICORN_BACKLOG:-256}"' not in start_text:
        findings.append("docker/start.sh no configura backlog de Gunicorn")

    for key in required_gunicorn_keys:
        if key not in compose_text:
            findings.append(f"compose.yaml no propaga {key}")

        if key not in parse_env_keys(local_env_text):
            findings.append(f"compose.env.example no define {key}")

        if key not in parse_env_keys(production_env_text):
            findings.append(f"compose.production.env.example no define {key}")

    nginx_fragments = (
        "limit_req_zone $binary_remote_addr",
        "limit_conn_zone $binary_remote_addr",
        "limit_req_status 429;",
        "limit_conn_status 429;",
        "limit_req zone=per_ip_requests burst=100 nodelay;",
        "limit_conn per_ip_connections 32;",
        "proxy_connect_timeout 5s;",
        "proxy_send_timeout 30s;",
        "proxy_read_timeout 65s;",
    )

    for fragment in nginx_fragments:
        if fragment not in nginx_text:
            findings.append(f"docker/nginx.conf no contiene {fragment}")

    return findings


def validate_media_outage_config(workflow_text):
    required_fragments = (
        "name: Probar interrupcion de escritura multimedia",
        "vapes-shop-media-outage:/app/backend/media",
        "vapes-shop-media-outage:/srv/media:ro",
        "verify_media_storage.py",
        "--expect unavailable",
        "chmod 0555 /media /media/operational",
        "chmod 0755 /media /media/operational",
        "/media/operational/persistent.txt",
        "media-recovery.json",
        'test "$restart_after" -eq "$MEDIA_WEB_RESTART_BEFORE"',
    )

    return [
        f"django-ci.yml no contiene {fragment}"
        for fragment in required_fragments
        if fragment not in workflow_text
    ]


def validate_database_outage_config(
    compose_text,
    local_env_text,
    production_env_text,
    workflow_text,
):
    findings = []
    database_keys = (
        "DJANGO_DB_CONN_MAX_AGE",
        "DJANGO_DB_CONNECT_TIMEOUT",
    )

    for key in database_keys:
        if f"${{{key}:-" not in compose_text:
            findings.append(f"compose.yaml no permite configurar {key}")

        if key not in parse_env_keys(local_env_text):
            findings.append(f"compose.env.example no define {key}")

        if key not in parse_env_keys(production_env_text):
            findings.append(f"compose.production.env.example no define {key}")

    workflow_fragments = (
        "name: Probar interrupcion temporal de MySQL",
        "verify_dependency_outage.py",
        "database-outage.json",
        "docker compose --env-file compose.env.example stop",
        "docker compose --env-file compose.env.example start db",
        "database-recovery.json",
        'test "$restart_after" -eq "$DATABASE_WEB_RESTART_BEFORE"',
        "database-outage-compose.log",
    )

    for fragment in workflow_fragments:
        if fragment not in workflow_text:
            findings.append(f"django-ci.yml no contiene {fragment}")

    return findings


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
        "cancel_fixture.py",
        "run /scripts/cancel.js",
        "cancel-invariants.json",
        "Probar canal concurrente de imagenes",
        "/performance/image_pipeline.py",
        "IMAGE_PIPELINE_TEST_ENABLED=true",
        "image-pipeline.json",
        "name: Probar recuperacion automatica",
        "run /scripts/recovery.js",
        "post-pressure-recovery.json",
        "post-crash-recovery.json",
        "docker exec \"$RESILIENCE_WEB_ID\" sh -c \"kill -KILL 1\"",
        "container-restart.json",
        "rm -f performance-runtime/checkout-fixture.json",
        "rm -f performance-runtime/coupon-fixture.json",
        "rm -f performance-runtime/cancel-fixture.json",
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
        "cancel": project_root / "performance" / "cancel.js",
        "cancel_fixture": (
            project_root / "performance" / "cancel_fixture.py"
        ),
        "image_pipeline": (
            project_root / "performance" / "image_pipeline.py"
        ),
        "recovery": project_root / "performance" / "recovery.js",
        "recovery_verifier": project_root / "scripts" / "verify_recovery.py",
        "dependency_outage_verifier": (
            project_root / "scripts" / "verify_dependency_outage.py"
        ),
        "media_storage_verifier": (
            project_root / "scripts" / "verify_media_storage.py"
        ),
        "backup_monitor": project_root / "scripts" / "monitor_backups.py",
        "external_backup": project_root / "scripts" / "external_backup.py",
        "backup_operations": (
            project_root / "scripts" / "backup_operations.py"
        ),
        "backup_dockerfile": project_root / "docker" / "backup.Dockerfile",
        "start": project_root / "docker" / "start.sh",
        "nginx": project_root / "docker" / "nginx.conf",
        "workflow": project_root / ".github" / "workflows" / "performance.yml",
        "django_workflow": (
            project_root / ".github" / "workflows" / "django-ci.yml"
        ),
        "production_compose": project_root / "compose.production.yaml",
        "deploy": project_root / "scripts" / "deploy_production.py",
        "backup_service": (
            project_root / "ops" / "systemd" / "vapes-shop-backup.service"
        ),
        "backup_timer": (
            project_root / "ops" / "systemd" / "vapes-shop-backup.timer"
        ),
        "monitor_service": (
            project_root
            / "ops"
            / "systemd"
            / "vapes-shop-production-monitor.service"
        ),
        "monitor_timer": (
            project_root
            / "ops"
            / "systemd"
            / "vapes-shop-production-monitor.timer"
        ),
        "drill_service": (
            project_root
            / "ops"
            / "systemd"
            / "vapes-shop-recovery-drill.service"
        ),
        "drill_timer": (
            project_root
            / "ops"
            / "systemd"
            / "vapes-shop-recovery-drill.timer"
        ),
        "schedule_env": (
            project_root
            / "ops"
            / "systemd"
            / "backup-operations.env.example"
        ),
        "monitor_env": (
            project_root
            / "ops"
            / "systemd"
            / "production-monitor.env.example"
        ),
        "host_bootstrap": (
            project_root
            / "ops"
            / "provision"
            / "ubuntu-bootstrap.sh"
        ),
        "host_readiness": (
            project_root / "scripts" / "check_host_readiness.py"
        ),
        "production_monitor": (
            project_root / "scripts" / "monitor_production.py"
        ),
        "production_recovery": (
            project_root / "scripts" / "recover_production.py"
        ),
        "disaster_docs": (
            project_root / "docs" / "DISASTER_RECOVERY.md"
        ),
        "release_manifest": (
            project_root / "scripts" / "release_manifest.py"
        ),
        "release_fetcher": (
            project_root / "scripts" / "fetch_release_manifest.py"
        ),
        "publish_workflow": (
            project_root / ".github" / "workflows" / "publish-images.yml"
        ),
        "secret_scan_workflow": (
            project_root / ".github" / "workflows" / "secret-scan.yml"
        ),
        "supply_chain_workflow": (
            project_root / ".github" / "workflows" / "supply-chain.yml"
        ),
        "codeowners": project_root / ".github" / "CODEOWNERS",
        "production_monitor_workflow": (
            project_root
            / ".github"
            / "workflows"
            / "production-monitor.yml"
        ),
        "host_docs": (
            project_root / "docs" / "HOST_PROVISIONING.md"
        ),
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
        validate_cancel_script(
            paths["cancel"].read_text(encoding="utf-8")
        )
    )
    findings.extend(
        validate_cancel_fixture(
            paths["cancel_fixture"].read_text(encoding="utf-8")
        )
    )
    findings.extend(
        validate_image_pipeline(
            paths["image_pipeline"].read_text(encoding="utf-8")
        )
    )
    findings.extend(
        validate_media_proxy(
            paths["nginx"].read_text(encoding="utf-8")
        )
    )
    findings.extend(
        validate_recovery_script(
            paths["recovery"].read_text(encoding="utf-8")
        )
    )
    findings.extend(
        validate_recovery_verifier(
            paths["recovery_verifier"].read_text(encoding="utf-8")
        )
    )
    findings.extend(
        validate_dependency_outage_verifier(
            paths["dependency_outage_verifier"].read_text(encoding="utf-8")
        )
    )
    findings.extend(
        validate_media_storage_verifier(
            paths["media_storage_verifier"].read_text(encoding="utf-8")
        )
    )
    findings.extend(
        validate_backup_monitor(
            paths["backup_monitor"].read_text(encoding="utf-8")
        )
    )
    findings.extend(
        validate_production_monitor(
            paths["production_monitor"].read_text(encoding="utf-8")
        )
    )
    findings.extend(
        validate_codeowners(
            paths["codeowners"].read_text(encoding="utf-8")
        )
    )
    findings.extend(
        validate_security_workflow_timeouts(
            paths["secret_scan_workflow"].read_text(encoding="utf-8"),
            paths["supply_chain_workflow"].read_text(encoding="utf-8"),
        )
    )
    findings.extend(
        validate_django_workflow_timeouts(
            paths["django_workflow"].read_text(encoding="utf-8")
        )
    )
    findings.extend(
        validate_publish_workflow_timeouts(
            paths["publish_workflow"].read_text(encoding="utf-8")
        )
    )
    findings.extend(
        validate_production_monitor_schedule(
            paths["monitor_service"].read_text(encoding="utf-8"),
            paths["monitor_timer"].read_text(encoding="utf-8"),
            paths["monitor_env"].read_text(encoding="utf-8"),
            paths["production_monitor_workflow"].read_text(
                encoding="utf-8"
            ),
            paths["django_workflow"].read_text(encoding="utf-8"),
            paths["host_bootstrap"].read_text(encoding="utf-8"),
            paths["host_docs"].read_text(encoding="utf-8"),
        )
    )
    findings.extend(
        validate_backup_monitor_config(
            paths["compose"].read_text(encoding="utf-8"),
            paths["production_compose"].read_text(encoding="utf-8"),
            paths["local_env"].read_text(encoding="utf-8"),
            paths["production_env"].read_text(encoding="utf-8"),
            paths["django_workflow"].read_text(encoding="utf-8"),
            paths["deploy"].read_text(encoding="utf-8"),
        )
    )
    findings.extend(
        validate_external_backup_script(
            paths["external_backup"].read_text(encoding="utf-8")
        )
    )
    findings.extend(
        validate_external_backup_config(
            paths["backup_dockerfile"].read_text(encoding="utf-8"),
            paths["compose"].read_text(encoding="utf-8"),
            paths["production_compose"].read_text(encoding="utf-8"),
            paths["local_env"].read_text(encoding="utf-8"),
            paths["production_env"].read_text(encoding="utf-8"),
            paths["django_workflow"].read_text(encoding="utf-8"),
            paths["deploy"].read_text(encoding="utf-8"),
        )
    )
    findings.extend(
        validate_disaster_recovery(
            paths["production_recovery"].read_text(encoding="utf-8"),
            paths["external_backup"].read_text(encoding="utf-8"),
            paths["deploy"].read_text(encoding="utf-8"),
            paths["compose"].read_text(encoding="utf-8"),
            paths["production_compose"].read_text(encoding="utf-8"),
            paths["local_env"].read_text(encoding="utf-8"),
            paths["production_env"].read_text(encoding="utf-8"),
            paths["django_workflow"].read_text(encoding="utf-8"),
            paths["disaster_docs"].read_text(encoding="utf-8"),
        )
    )
    findings.extend(
        validate_release_manifest(
            paths["release_manifest"].read_text(encoding="utf-8"),
            paths["release_fetcher"].read_text(encoding="utf-8"),
            paths["production_recovery"].read_text(encoding="utf-8"),
            paths["publish_workflow"].read_text(encoding="utf-8"),
            paths["disaster_docs"].read_text(encoding="utf-8"),
            paths["host_bootstrap"].read_text(encoding="utf-8"),
            paths["host_readiness"].read_text(encoding="utf-8"),
        )
    )
    findings.extend(
        validate_backup_operations(
            paths["backup_operations"].read_text(encoding="utf-8")
        )
    )
    findings.extend(
        validate_backup_schedule(
            paths["local_env"].read_text(encoding="utf-8"),
            paths["production_env"].read_text(encoding="utf-8"),
            paths["django_workflow"].read_text(encoding="utf-8"),
            paths["backup_service"].read_text(encoding="utf-8"),
            paths["backup_timer"].read_text(encoding="utf-8"),
            paths["drill_service"].read_text(encoding="utf-8"),
            paths["drill_timer"].read_text(encoding="utf-8"),
            paths["schedule_env"].read_text(encoding="utf-8"),
        )
    )
    findings.extend(
        validate_host_provisioning(
            paths["host_bootstrap"].read_text(encoding="utf-8"),
            paths["host_readiness"].read_text(encoding="utf-8"),
            paths["deploy"].read_text(encoding="utf-8"),
            paths["compose"].read_text(encoding="utf-8"),
            paths["local_env"].read_text(encoding="utf-8"),
            paths["production_env"].read_text(encoding="utf-8"),
            paths["django_workflow"].read_text(encoding="utf-8"),
        )
    )
    findings.extend(
        validate_resilience_config(
            paths["start"].read_text(encoding="utf-8"),
            paths["nginx"].read_text(encoding="utf-8"),
            paths["compose"].read_text(encoding="utf-8"),
            paths["local_env"].read_text(encoding="utf-8"),
            paths["production_env"].read_text(encoding="utf-8"),
        )
    )
    findings.extend(
        validate_database_outage_config(
            paths["compose"].read_text(encoding="utf-8"),
            paths["local_env"].read_text(encoding="utf-8"),
            paths["production_env"].read_text(encoding="utf-8"),
            paths["django_workflow"].read_text(encoding="utf-8"),
        )
    )
    findings.extend(
        validate_media_outage_config(
            paths["django_workflow"].read_text(encoding="utf-8")
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
