import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "check_capacity_config.py"
SPEC = importlib.util.spec_from_file_location(
    "check_capacity_config",
    SCRIPT_PATH,
)
capacity = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(capacity)
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class CapacityConfigTests(unittest.TestCase):
    def test_repository_capacity_policy_is_complete(self):
        self.assertEqual(
            capacity.find_capacity_findings(PROJECT_ROOT),
            [],
        )

    def test_compose_without_memory_limit_is_rejected(self):
        compose_text = (PROJECT_ROOT / "compose.yaml").read_text(
            encoding="utf-8",
        )
        invalid_text = compose_text.replace(
            "    mem_limit: ${DB_MEMORY_LIMIT:-768m}\n",
            "",
            1,
        )

        findings = capacity.validate_compose(invalid_text)

        self.assertIn("db no define mem_limit", findings)

    def test_environment_without_resource_variable_is_rejected(self):
        env_text = (PROJECT_ROOT / "compose.env.example").read_text(
            encoding="utf-8",
        )
        invalid_text = env_text.replace("WEB_CPU_LIMIT=1.00\n", "", 1)

        findings = capacity.validate_env(invalid_text, "compose.env.example")

        self.assertIn(
            "compose.env.example no define WEB_CPU_LIMIT",
            findings,
        )

    def test_production_environment_without_debug_false_is_rejected(self):
        compose_text = (PROJECT_ROOT / "compose.yaml").read_text(
            encoding="utf-8",
        )
        local_env_text = (PROJECT_ROOT / "compose.env.example").read_text(
            encoding="utf-8",
        )
        production_env_text = (
            PROJECT_ROOT / "compose.production.env.example"
        ).read_text(encoding="utf-8")
        invalid_text = production_env_text.replace(
            "DJANGO_DEBUG=False\n",
            "",
            1,
        )

        findings = capacity.validate_environment_security_defaults(
            compose_text,
            local_env_text,
            invalid_text,
        )

        self.assertIn(
            (
                "compose.production.env.example debe declarar "
                "DJANGO_DEBUG=False"
            ),
            findings,
        )

    def test_production_environment_without_permissions_policy_is_rejected(
        self,
    ):
        compose_text = (PROJECT_ROOT / "compose.yaml").read_text(
            encoding="utf-8",
        )
        local_env_text = (PROJECT_ROOT / "compose.env.example").read_text(
            encoding="utf-8",
        )
        production_env_text = (
            PROJECT_ROOT / "compose.production.env.example"
        ).read_text(encoding="utf-8")
        invalid_text = production_env_text.replace(
            "microphone=(), ",
            "",
            1,
        )

        findings = capacity.validate_environment_security_defaults(
            compose_text,
            local_env_text,
            invalid_text,
        )

        self.assertIn(
            (
                "compose.production.env.example debe restringir "
                "DJANGO_PERMISSIONS_POLICY con microphone=()"
            ),
            findings,
        )

    def test_production_environment_without_json_logs_is_rejected(self):
        compose_text = (PROJECT_ROOT / "compose.yaml").read_text(
            encoding="utf-8",
        )
        local_env_text = (PROJECT_ROOT / "compose.env.example").read_text(
            encoding="utf-8",
        )
        production_env_text = (
            PROJECT_ROOT / "compose.production.env.example"
        ).read_text(encoding="utf-8")
        invalid_text = production_env_text.replace(
            "DJANGO_LOG_FORMAT=json\n",
            "",
            1,
        )

        findings = capacity.validate_environment_security_defaults(
            compose_text,
            local_env_text,
            invalid_text,
        )

        self.assertIn(
            (
                "compose.production.env.example debe declarar "
                "DJANGO_LOG_FORMAT=json"
            ),
            findings,
        )

    def test_production_environment_without_session_age_limit_is_rejected(
        self,
    ):
        compose_text = (PROJECT_ROOT / "compose.yaml").read_text(
            encoding="utf-8",
        )
        local_env_text = (PROJECT_ROOT / "compose.env.example").read_text(
            encoding="utf-8",
        )
        production_env_text = (
            PROJECT_ROOT / "compose.production.env.example"
        ).read_text(encoding="utf-8")
        invalid_text = production_env_text.replace(
            "DJANGO_SESSION_COOKIE_AGE=604800\n",
            "",
            1,
        )

        findings = capacity.validate_environment_security_defaults(
            compose_text,
            local_env_text,
            invalid_text,
        )

        self.assertIn(
            (
                "compose.production.env.example debe declarar "
                "DJANGO_SESSION_COOKIE_AGE=604800"
            ),
            findings,
        )

    def test_production_environment_without_password_minimum_is_rejected(
        self,
    ):
        compose_text = (PROJECT_ROOT / "compose.yaml").read_text(
            encoding="utf-8",
        )
        local_env_text = (PROJECT_ROOT / "compose.env.example").read_text(
            encoding="utf-8",
        )
        production_env_text = (
            PROJECT_ROOT / "compose.production.env.example"
        ).read_text(encoding="utf-8")
        invalid_text = production_env_text.replace(
            "DJANGO_PASSWORD_MIN_LENGTH=12\n",
            "",
            1,
        )

        findings = capacity.validate_environment_security_defaults(
            compose_text,
            local_env_text,
            invalid_text,
        )

        self.assertIn(
            (
                "compose.production.env.example debe declarar "
                "DJANGO_PASSWORD_MIN_LENGTH=12"
            ),
            findings,
        )

    def test_production_environment_without_upload_memory_limit_is_rejected(
        self,
    ):
        compose_text = (PROJECT_ROOT / "compose.yaml").read_text(
            encoding="utf-8",
        )
        local_env_text = (PROJECT_ROOT / "compose.env.example").read_text(
            encoding="utf-8",
        )
        production_env_text = (
            PROJECT_ROOT / "compose.production.env.example"
        ).read_text(encoding="utf-8")
        invalid_text = production_env_text.replace(
            "DJANGO_DATA_UPLOAD_MAX_MEMORY_SIZE=1048576\n",
            "",
            1,
        )

        findings = capacity.validate_environment_security_defaults(
            compose_text,
            local_env_text,
            invalid_text,
        )

        self.assertIn(
            (
                "compose.production.env.example debe declarar "
                "DJANGO_DATA_UPLOAD_MAX_MEMORY_SIZE=1048576"
            ),
            findings,
        )

    def test_compose_without_security_env_propagation_is_rejected(self):
        compose_text = (PROJECT_ROOT / "compose.yaml").read_text(
            encoding="utf-8",
        )
        local_env_text = (PROJECT_ROOT / "compose.env.example").read_text(
            encoding="utf-8",
        )
        production_env_text = (
            PROJECT_ROOT / "compose.production.env.example"
        ).read_text(encoding="utf-8")
        invalid_compose = compose_text.replace(
            "  DJANGO_DEBUG: ${DJANGO_DEBUG:-False}\n",
            '  DJANGO_DEBUG: "False"\n',
            1,
        )

        findings = capacity.validate_environment_security_defaults(
            invalid_compose,
            local_env_text,
            production_env_text,
        )

        self.assertIn("compose.yaml debe propagar DJANGO_DEBUG", findings)

    def test_production_check_without_password_hasher_guard_is_rejected(
        self,
    ):
        production_check_text = (
            PROJECT_ROOT
            / "backend"
            / "store"
            / "management"
            / "commands"
            / "production_check.py"
        ).read_text(encoding="utf-8")
        invalid_text = production_check_text.replace(
            "PASSWORD_HASHERS no debe incluir hashers debiles o sin sal.",
            "",
            1,
        )

        findings = capacity.validate_production_check_security(invalid_text)

        self.assertIn(
            (
                "production_check.py no contiene PASSWORD_HASHERS no debe "
                "incluir hashers debiles o sin sal."
            ),
            findings,
        )

    def test_production_check_without_upload_limit_guard_is_rejected(self):
        production_check_text = (
            PROJECT_ROOT
            / "backend"
            / "store"
            / "management"
            / "commands"
            / "production_check.py"
        ).read_text(encoding="utf-8")
        invalid_text = production_check_text.replace(
            "DJANGO_DATA_UPLOAD_MAX_MEMORY_SIZE",
            "",
            1,
        )

        findings = capacity.validate_production_check_security(invalid_text)

        self.assertIn(
            "production_check.py no contiene DJANGO_DATA_UPLOAD_MAX_MEMORY_SIZE",
            findings,
        )

    def test_mutable_k6_image_is_rejected(self):
        workflow_text = (
            PROJECT_ROOT / ".github" / "workflows" / "performance.yml"
        ).read_text(encoding="utf-8")
        invalid_text = capacity.K6_IMAGE_PATTERN.sub(
            "grafana/k6:2.0.0",
            workflow_text,
        )

        findings = capacity.validate_workflow(invalid_text)

        self.assertIn(
            "performance.yml no fija k6 2.0.0 por digest",
            findings,
        )

    def test_checkout_without_csrf_is_rejected(self):
        checkout_text = (
            PROJECT_ROOT / "performance" / "checkout.js"
        ).read_text(encoding="utf-8")
        invalid_text = checkout_text.replace(
            "'X-CSRFToken': buyer.csrf_token,\n",
            "",
            1,
        )

        findings = capacity.validate_checkout_script(invalid_text)

        self.assertIn(
            "performance/checkout.js no contiene "
            "'X-CSRFToken': buyer.csrf_token",
            findings,
        )

    def test_checkout_fixture_without_database_guard_is_rejected(self):
        fixture_text = (
            PROJECT_ROOT / "performance" / "checkout_fixture.py"
        ).read_text(encoding="utf-8")
        invalid_text = fixture_text.replace(
            "CHECKOUT_LOAD_TEST_ENABLED",
            "UNSAFE_LOAD_TEST_ENABLED",
        )

        findings = capacity.validate_checkout_fixture(invalid_text)

        self.assertIn(
            "performance/checkout_fixture.py no contiene "
            "CHECKOUT_LOAD_TEST_ENABLED",
            findings,
        )

    def test_coupon_without_limit_rejection_is_rejected(self):
        coupon_text = (
            PROJECT_ROOT / "performance" / "coupon.js"
        ).read_text(encoding="utf-8")
        invalid_text = coupon_text.replace(
            "body.coupon_invalid === true",
            "body.coupon_invalid === false",
            1,
        )

        findings = capacity.validate_coupon_script(invalid_text)

        self.assertIn(
            "performance/coupon.js no contiene "
            "body.coupon_invalid === true",
            findings,
        )

    def test_coupon_fixture_without_usage_invariant_is_rejected(self):
        fixture_text = (
            PROJECT_ROOT / "performance" / "coupon_fixture.py"
        ).read_text(encoding="utf-8")
        invalid_text = fixture_text.replace(
            "coupon_usage_matches_limit",
            "coupon_usage_not_checked",
        )

        findings = capacity.validate_coupon_fixture(invalid_text)

        self.assertIn(
            "performance/coupon_fixture.py no contiene "
            "coupon_usage_matches_limit",
            findings,
        )

    def test_cancel_without_closed_rejection_is_rejected(self):
        cancel_text = (
            PROJECT_ROOT / "performance" / "cancel.js"
        ).read_text(encoding="utf-8")
        invalid_text = cancel_text.replace(
            "body.error.toLowerCase().includes('cerrada')",
            "body.error.toLowerCase().includes('otra-causa')",
            1,
        )

        findings = capacity.validate_cancel_script(invalid_text)

        self.assertIn(
            "performance/cancel.js no contiene "
            "body.error.toLowerCase().includes('cerrada')",
            findings,
        )

    def test_cancel_fixture_without_unique_restore_is_rejected(self):
        fixture_text = (
            PROJECT_ROOT / "performance" / "cancel_fixture.py"
        ).read_text(encoding="utf-8")
        invalid_text = fixture_text.replace(
            "restore_movement_created_once",
            "restore_movement_not_checked",
        )

        findings = capacity.validate_cancel_fixture(invalid_text)

        self.assertIn(
            "performance/cancel_fixture.py no contiene "
            "restore_movement_created_once",
            findings,
        )

    def test_image_pipeline_without_sanitization_is_rejected(self):
        pipeline_text = (
            PROJECT_ROOT / "performance" / "image_pipeline.py"
        ).read_text(encoding="utf-8")
        invalid_text = pipeline_text.replace(
            "sanitize_product_image",
            "unsafe_image_passthrough",
        )

        findings = capacity.validate_image_pipeline(invalid_text)

        self.assertIn(
            "performance/image_pipeline.py no contiene "
            "sanitize_product_image",
            findings,
        )

    def test_media_proxy_without_corp_is_rejected(self):
        nginx_text = (
            PROJECT_ROOT / "docker" / "nginx.conf"
        ).read_text(encoding="utf-8")
        invalid_text = nginx_text.replace(
            "add_header Cross-Origin-Resource-Policy same-origin always;\n",
            "",
            1,
        )

        findings = capacity.validate_media_proxy(invalid_text)

        self.assertIn(
            "docker/nginx.conf no contiene "
            "add_header Cross-Origin-Resource-Policy same-origin always;",
            findings,
        )

    def test_recovery_script_without_load_shedding_is_rejected(self):
        recovery_text = (
            PROJECT_ROOT / "performance" / "recovery.js"
        ).read_text(encoding="utf-8")
        invalid_text = recovery_text.replace(
            "pressure_shed",
            "pressure_not_measured",
        )

        findings = capacity.validate_recovery_script(invalid_text)

        self.assertIn(
            "performance/recovery.js no contiene pressure_shed",
            findings,
        )

    def test_recovery_verifier_without_stability_is_rejected(self):
        verifier_text = (
            PROJECT_ROOT / "scripts" / "verify_recovery.py"
        ).read_text(encoding="utf-8")
        invalid_text = verifier_text.replace(
            "consecutive_successes",
            "single_success",
        )

        findings = capacity.validate_recovery_verifier(invalid_text)

        self.assertIn(
            "scripts/verify_recovery.py no contiene consecutive_successes",
            findings,
        )

    def test_recovery_verifier_without_report_symlink_guard_is_rejected(self):
        verifier_text = (
            PROJECT_ROOT / "scripts" / "verify_recovery.py"
        ).read_text(encoding="utf-8")
        invalid_text = verifier_text.replace(
            "temporary_path.is_symlink()",
            "False",
            1,
        )

        findings = capacity.validate_recovery_verifier(invalid_text)

        self.assertIn(
            (
                "scripts/verify_recovery.py no contiene "
                "temporary_path.is_symlink()"
            ),
            findings,
        )

    def test_resilience_config_without_backlog_is_rejected(self):
        start_text = (
            PROJECT_ROOT / "docker" / "start.sh"
        ).read_text(encoding="utf-8")
        nginx_text = (
            PROJECT_ROOT / "docker" / "nginx.conf"
        ).read_text(encoding="utf-8")
        compose_text = (
            PROJECT_ROOT / "compose.yaml"
        ).read_text(encoding="utf-8")
        local_env_text = (
            PROJECT_ROOT / "compose.env.example"
        ).read_text(encoding="utf-8")
        production_env_text = (
            PROJECT_ROOT / "compose.production.env.example"
        ).read_text(encoding="utf-8")
        invalid_start = start_text.replace(
            '    --backlog "${GUNICORN_BACKLOG:-256}" \\\n',
            "",
            1,
        )

        findings = capacity.validate_resilience_config(
            invalid_start,
            nginx_text,
            compose_text,
            local_env_text,
            production_env_text,
        )

        self.assertIn(
            "docker/start.sh no configura backlog de Gunicorn",
            findings,
        )

    def test_resilience_config_without_gunicorn_header_limits_is_rejected(
        self,
    ):
        start_text = (
            PROJECT_ROOT / "docker" / "start.sh"
        ).read_text(encoding="utf-8")
        nginx_text = (
            PROJECT_ROOT / "docker" / "nginx.conf"
        ).read_text(encoding="utf-8")
        compose_text = (
            PROJECT_ROOT / "compose.yaml"
        ).read_text(encoding="utf-8")
        local_env_text = (
            PROJECT_ROOT / "compose.env.example"
        ).read_text(encoding="utf-8")
        production_env_text = (
            PROJECT_ROOT / "compose.production.env.example"
        ).read_text(encoding="utf-8")
        invalid_start = start_text.replace(
            '    --limit-request-fields "${GUNICORN_LIMIT_REQUEST_FIELDS:-100}" \\\n',
            "",
            1,
        )

        findings = capacity.validate_resilience_config(
            invalid_start,
            nginx_text,
            compose_text,
            local_env_text,
            production_env_text,
        )

        self.assertIn(
            (
                "docker/start.sh no contiene "
                '--limit-request-fields "${GUNICORN_LIMIT_REQUEST_FIELDS:-100}"'
            ),
            findings,
        )

    def test_nginx_forwarded_for_chain_is_rejected(self):
        start_text = (
            PROJECT_ROOT / "docker" / "start.sh"
        ).read_text(encoding="utf-8")
        nginx_text = (
            PROJECT_ROOT / "docker" / "nginx.conf"
        ).read_text(encoding="utf-8")
        compose_text = (
            PROJECT_ROOT / "compose.yaml"
        ).read_text(encoding="utf-8")
        local_env_text = (
            PROJECT_ROOT / "compose.env.example"
        ).read_text(encoding="utf-8")
        production_env_text = (
            PROJECT_ROOT / "compose.production.env.example"
        ).read_text(encoding="utf-8")
        invalid_nginx = nginx_text.replace(
            "proxy_set_header X-Forwarded-For $remote_addr;",
            "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
            1,
        )

        findings = capacity.validate_resilience_config(
            start_text,
            invalid_nginx,
            compose_text,
            local_env_text,
            production_env_text,
        )

        self.assertIn(
            "docker/nginx.conf no debe propagar X-Forwarded-For del cliente",
            findings,
        )

    def test_nginx_without_header_timeout_is_rejected(self):
        start_text = (
            PROJECT_ROOT / "docker" / "start.sh"
        ).read_text(encoding="utf-8")
        nginx_text = (
            PROJECT_ROOT / "docker" / "nginx.conf"
        ).read_text(encoding="utf-8")
        compose_text = (
            PROJECT_ROOT / "compose.yaml"
        ).read_text(encoding="utf-8")
        local_env_text = (
            PROJECT_ROOT / "compose.env.example"
        ).read_text(encoding="utf-8")
        production_env_text = (
            PROJECT_ROOT / "compose.production.env.example"
        ).read_text(encoding="utf-8")
        invalid_nginx = nginx_text.replace(
            "    client_header_timeout 10s;\n",
            "",
            1,
        )

        findings = capacity.validate_resilience_config(
            start_text,
            invalid_nginx,
            compose_text,
            local_env_text,
            production_env_text,
        )

        self.assertIn(
            "docker/nginx.conf no contiene client_header_timeout 10s;",
            findings,
        )

    def test_nginx_without_body_size_limit_is_rejected(self):
        start_text = (
            PROJECT_ROOT / "docker" / "start.sh"
        ).read_text(encoding="utf-8")
        nginx_text = (
            PROJECT_ROOT / "docker" / "nginx.conf"
        ).read_text(encoding="utf-8")
        compose_text = (
            PROJECT_ROOT / "compose.yaml"
        ).read_text(encoding="utf-8")
        local_env_text = (
            PROJECT_ROOT / "compose.env.example"
        ).read_text(encoding="utf-8")
        production_env_text = (
            PROJECT_ROOT / "compose.production.env.example"
        ).read_text(encoding="utf-8")
        invalid_nginx = nginx_text.replace(
            "        client_max_body_size 6m;\n",
            "",
            1,
        )

        findings = capacity.validate_resilience_config(
            start_text,
            invalid_nginx,
            compose_text,
            local_env_text,
            production_env_text,
        )

        self.assertIn(
            "docker/nginx.conf no contiene client_max_body_size 6m;",
            findings,
        )

    def test_dependency_outage_verifier_without_database_state_is_rejected(self):
        verifier_text = (
            PROJECT_ROOT / "scripts" / "verify_dependency_outage.py"
        ).read_text(encoding="utf-8")
        invalid_text = verifier_text.replace(
            'database": "unavailable"',
            'database": "unknown"',
        )

        findings = capacity.validate_dependency_outage_verifier(
            invalid_text
        )

        self.assertIn(
            (
                "scripts/verify_dependency_outage.py no contiene "
                'database": "unavailable"'
            ),
            findings,
        )

    def test_dependency_outage_verifier_without_report_guard_is_rejected(self):
        verifier_text = (
            PROJECT_ROOT / "scripts" / "verify_dependency_outage.py"
        ).read_text(encoding="utf-8")
        invalid_text = verifier_text.replace(
            "temporary_path.is_symlink()",
            "False",
            1,
        )

        findings = capacity.validate_dependency_outage_verifier(
            invalid_text
        )

        self.assertIn(
            (
                "scripts/verify_dependency_outage.py no contiene "
                "temporary_path.is_symlink()"
            ),
            findings,
        )

    def test_database_outage_config_without_connect_timeout_is_rejected(self):
        compose_text = (
            PROJECT_ROOT / "compose.yaml"
        ).read_text(encoding="utf-8")
        local_env_text = (
            PROJECT_ROOT / "compose.env.example"
        ).read_text(encoding="utf-8")
        production_env_text = (
            PROJECT_ROOT / "compose.production.env.example"
        ).read_text(encoding="utf-8")
        workflow_text = (
            PROJECT_ROOT / ".github" / "workflows" / "django-ci.yml"
        ).read_text(encoding="utf-8")
        invalid_compose = compose_text.replace(
            "  DJANGO_DB_CONNECT_TIMEOUT: ${DJANGO_DB_CONNECT_TIMEOUT:-10}\n",
            "",
            1,
        )

        findings = capacity.validate_database_outage_config(
            invalid_compose,
            local_env_text,
            production_env_text,
            workflow_text,
        )

        self.assertIn(
            "compose.yaml no permite configurar DJANGO_DB_CONNECT_TIMEOUT",
            findings,
        )

    def test_database_outage_workflow_without_restart_guard_is_rejected(self):
        compose_text = (
            PROJECT_ROOT / "compose.yaml"
        ).read_text(encoding="utf-8")
        local_env_text = (
            PROJECT_ROOT / "compose.env.example"
        ).read_text(encoding="utf-8")
        production_env_text = (
            PROJECT_ROOT / "compose.production.env.example"
        ).read_text(encoding="utf-8")
        workflow_text = (
            PROJECT_ROOT / ".github" / "workflows" / "django-ci.yml"
        ).read_text(encoding="utf-8")
        invalid_workflow = workflow_text.replace(
            'test "$restart_after" -eq "$DATABASE_WEB_RESTART_BEFORE"',
            "true",
            1,
        )

        findings = capacity.validate_database_outage_config(
            compose_text,
            local_env_text,
            production_env_text,
            invalid_workflow,
        )

        self.assertIn(
            (
                "django-ci.yml no contiene "
                'test "$restart_after" -eq "$DATABASE_WEB_RESTART_BEFORE"'
            ),
            findings,
        )

    def test_media_storage_verifier_without_cleanup_is_rejected(self):
        verifier_text = (
            PROJECT_ROOT / "scripts" / "verify_media_storage.py"
        ).read_text(encoding="utf-8")
        invalid_text = verifier_text.replace(
            "storage.delete(saved_name)",
            "pass",
            1,
        )

        findings = capacity.validate_media_storage_verifier(invalid_text)

        self.assertIn(
            (
                "scripts/verify_media_storage.py no contiene "
                "storage.delete(saved_name)"
            ),
            findings,
        )

    def test_media_storage_verifier_without_report_guard_is_rejected(self):
        verifier_text = (
            PROJECT_ROOT / "scripts" / "verify_media_storage.py"
        ).read_text(encoding="utf-8")
        invalid_text = verifier_text.replace(
            "temporary_path.is_symlink()",
            "False",
            1,
        )

        findings = capacity.validate_media_storage_verifier(invalid_text)

        self.assertIn(
            (
                "scripts/verify_media_storage.py no contiene "
                "temporary_path.is_symlink()"
            ),
            findings,
        )

    def test_media_outage_workflow_without_read_only_failure_is_rejected(self):
        workflow_text = (
            PROJECT_ROOT / ".github" / "workflows" / "django-ci.yml"
        ).read_text(encoding="utf-8")
        invalid_text = workflow_text.replace(
            "chmod 0555 /media /media/operational",
            "chmod 0755 /media /media/operational",
            1,
        )

        findings = capacity.validate_media_outage_config(invalid_text)

        self.assertIn(
            (
                "django-ci.yml no contiene "
                "chmod 0555 /media /media/operational"
            ),
            findings,
        )

    def test_media_outage_workflow_without_restart_guard_is_rejected(self):
        workflow_text = (
            PROJECT_ROOT / ".github" / "workflows" / "django-ci.yml"
        ).read_text(encoding="utf-8")
        invalid_text = workflow_text.replace(
            'test "$restart_after" -eq "$MEDIA_WEB_RESTART_BEFORE"',
            "true",
            1,
        )

        findings = capacity.validate_media_outage_config(invalid_text)

        self.assertIn(
            (
                "django-ci.yml no contiene "
                'test "$restart_after" -eq "$MEDIA_WEB_RESTART_BEFORE"'
            ),
            findings,
        )

    def test_backup_monitor_without_checksum_verification_is_rejected(self):
        monitor_text = (
            PROJECT_ROOT / "scripts" / "monitor_backups.py"
        ).read_text(encoding="utf-8")
        invalid_text = monitor_text.replace(
            "sha256_file",
            "checksum_not_verified",
        )

        findings = capacity.validate_backup_monitor(invalid_text)

        self.assertIn(
            "scripts/monitor_backups.py no contiene sha256_file",
            findings,
        )

    def test_backup_monitor_without_report_guard_is_rejected(self):
        monitor_text = (
            PROJECT_ROOT / "scripts" / "monitor_backups.py"
        ).read_text(encoding="utf-8")
        invalid_text = monitor_text.replace(
            "temporary_path.is_symlink()",
            "False",
            1,
        )

        findings = capacity.validate_backup_monitor(invalid_text)

        self.assertIn(
            (
                "scripts/monitor_backups.py no contiene "
                "temporary_path.is_symlink()"
            ),
            findings,
        )

    def test_production_monitor_without_report_output_is_rejected(self):
        monitor_text = (
            PROJECT_ROOT / "scripts" / "monitor_production.py"
        ).read_text(encoding="utf-8")
        invalid_text = monitor_text.replace(
            "MONITOR_REPORT_PATH",
            "UNSAFE_MONITOR_REPORT_ENV",
            1,
        )

        findings = capacity.validate_production_monitor(invalid_text)

        self.assertIn(
            (
                "scripts/monitor_production.py no contiene "
                "MONITOR_REPORT_PATH"
            ),
            findings,
        )

    def test_production_monitor_without_report_guard_is_rejected(self):
        monitor_text = (
            PROJECT_ROOT / "scripts" / "monitor_production.py"
        ).read_text(encoding="utf-8")
        invalid_text = monitor_text.replace(
            "temporary_path.is_symlink()",
            "False",
            1,
        )

        findings = capacity.validate_production_monitor(invalid_text)

        self.assertIn(
            (
                "scripts/monitor_production.py no contiene "
                "temporary_path.is_symlink()"
            ),
            findings,
        )

    def test_production_monitor_without_report_error_is_rejected(self):
        monitor_text = (
            PROJECT_ROOT / "scripts" / "monitor_production.py"
        ).read_text(encoding="utf-8")
        invalid_text = monitor_text.replace(
            "report_error",
            "report_failure",
            1,
        )

        findings = capacity.validate_production_monitor(invalid_text)

        self.assertIn(
            "scripts/monitor_production.py no contiene report_error",
            findings,
        )

    def test_codeowners_without_operations_owner_is_rejected(self):
        codeowners_text = (
            PROJECT_ROOT / ".github" / "CODEOWNERS"
        ).read_text(encoding="utf-8")
        invalid_text = codeowners_text.replace(
            "/ops/systemd/ @Alejandro-Arango\n",
            "",
            1,
        )

        findings = capacity.validate_codeowners(invalid_text)

        self.assertIn(
            "CODEOWNERS no contiene /ops/systemd/ @Alejandro-Arango",
            findings,
        )

    def test_codeowners_without_monitor_owner_is_rejected(self):
        codeowners_text = (
            PROJECT_ROOT / ".github" / "CODEOWNERS"
        ).read_text(encoding="utf-8")
        invalid_text = codeowners_text.replace(
            "/scripts/monitor_production.py @Alejandro-Arango\n",
            "",
            1,
        )

        findings = capacity.validate_codeowners(invalid_text)

        self.assertIn(
            (
                "CODEOWNERS no contiene "
                "/scripts/monitor_production.py @Alejandro-Arango"
            ),
            findings,
        )

    def test_secret_scan_without_timeout_is_rejected(self):
        secret_scan_text = (
            PROJECT_ROOT / ".github" / "workflows" / "secret-scan.yml"
        ).read_text(encoding="utf-8")
        supply_chain_text = (
            PROJECT_ROOT / ".github" / "workflows" / "supply-chain.yml"
        ).read_text(encoding="utf-8")
        invalid_secret_scan = secret_scan_text.replace(
            "    timeout-minutes: 15\n",
            "",
            1,
        )

        findings = capacity.validate_security_workflow_timeouts(
            invalid_secret_scan,
            supply_chain_text,
        )

        self.assertIn(
            "secret-scan.yml no limita gitleaks a 15 minutos",
            findings,
        )

    def test_supply_chain_without_image_timeout_is_rejected(self):
        secret_scan_text = (
            PROJECT_ROOT / ".github" / "workflows" / "secret-scan.yml"
        ).read_text(encoding="utf-8")
        supply_chain_text = (
            PROJECT_ROOT / ".github" / "workflows" / "supply-chain.yml"
        ).read_text(encoding="utf-8")
        invalid_supply_chain = supply_chain_text.replace(
            "    timeout-minutes: 30\n",
            "",
            1,
        )

        findings = capacity.validate_security_workflow_timeouts(
            secret_scan_text,
            invalid_supply_chain,
        )

        self.assertIn(
            "supply-chain.yml no limita container-images a 30 minutos",
            findings,
        )

    def test_django_ci_without_validate_timeout_is_rejected(self):
        workflow_text = (
            PROJECT_ROOT / ".github" / "workflows" / "django-ci.yml"
        ).read_text(encoding="utf-8")
        invalid_text = workflow_text.replace(
            "    timeout-minutes: 20\n",
            "",
            1,
        )

        findings = capacity.validate_django_workflow_timeouts(invalid_text)

        self.assertIn(
            "django-ci.yml no limita validate a 20 minutos",
            findings,
        )

    def test_django_ci_without_recovery_timeout_is_rejected(self):
        workflow_text = (
            PROJECT_ROOT / ".github" / "workflows" / "django-ci.yml"
        ).read_text(encoding="utf-8")
        invalid_text = workflow_text.replace(
            "    timeout-minutes: 30\n",
            "",
            1,
        )

        findings = capacity.validate_django_workflow_timeouts(invalid_text)

        self.assertIn(
            "django-ci.yml no limita recovery a 30 minutos",
            findings,
        )

    def test_publish_images_without_release_validation_timeout_is_rejected(
        self,
    ):
        workflow_text = (
            PROJECT_ROOT / ".github" / "workflows" / "publish-images.yml"
        ).read_text(encoding="utf-8")
        invalid_text = workflow_text.replace(
            "    timeout-minutes: 30\n",
            "",
            1,
        )

        findings = capacity.validate_publish_workflow_timeouts(invalid_text)

        self.assertIn(
            "publish-images.yml no limita validate a 30 minutos",
            findings,
        )

    def test_publish_images_without_publish_timeout_is_rejected(self):
        workflow_text = (
            PROJECT_ROOT / ".github" / "workflows" / "publish-images.yml"
        ).read_text(encoding="utf-8")
        invalid_text = workflow_text.replace(
            "    timeout-minutes: 45\n",
            "",
            1,
        )

        findings = capacity.validate_publish_workflow_timeouts(invalid_text)

        self.assertIn(
            "publish-images.yml no limita publish a 45 minutos",
            findings,
        )

    def test_official_action_major_tag_is_rejected(self):
        findings = capacity.validate_official_action_pins(
            {
                "ci.yml": (
                    "steps:\n"
                    "  - uses: actions/checkout@v4\n"
                    "  - uses: github/codeql-action/init@v3\n"
                ),
            },
        )

        self.assertIn(
            "ci.yml usa accion sin SHA: actions/checkout@v4",
            findings,
        )
        self.assertIn(
            "ci.yml usa accion sin SHA: github/codeql-action/init@v3",
            findings,
        )

    def test_dependabot_without_docker_directory_is_rejected(self):
        dependabot_text = (
            PROJECT_ROOT / ".github" / "dependabot.yml"
        ).read_text(encoding="utf-8")
        invalid_text = dependabot_text.replace(
            "  - package-ecosystem: docker\n"
            "    directory: /docker\n"
            "    schedule:\n"
            "      interval: weekly\n"
            "      day: monday\n"
            "      time: \"10:30\"\n"
            "      timezone: America/Bogota\n"
            "    open-pull-requests-limit: 3\n"
            "    groups:\n"
            "      operations-container-images:\n"
            "        update-types:\n"
            "          - minor\n"
            "          - patch\n",
            "",
            1,
        )

        findings = capacity.validate_dependabot_config(invalid_text)

        self.assertIn(
            (
                "dependabot.yml no configura imagenes Docker operativas "
                "(docker en /docker)"
            ),
            findings,
        )

    def test_dependabot_without_weekly_schedule_is_rejected(self):
        dependabot_text = (
            PROJECT_ROOT / ".github" / "dependabot.yml"
        ).read_text(encoding="utf-8")
        invalid_text = dependabot_text.replace(
            "      interval: weekly\n",
            "      interval: monthly\n",
            1,
        )

        findings = capacity.validate_dependabot_config(invalid_text)

        self.assertIn(
            "dependabot.yml no fija interval: weekly para dependencias Python",
            findings,
        )

    def production_monitor_schedule_inputs(self):
        systemd_root = PROJECT_ROOT / "ops" / "systemd"
        return {
            "monitor_service_text": (
                systemd_root / "vapes-shop-production-monitor.service"
            ).read_text(encoding="utf-8"),
            "monitor_timer_text": (
                systemd_root / "vapes-shop-production-monitor.timer"
            ).read_text(encoding="utf-8"),
            "monitor_env_text": (
                systemd_root / "production-monitor.env.example"
            ).read_text(encoding="utf-8"),
            "monitor_workflow_text": (
                PROJECT_ROOT
                / ".github"
                / "workflows"
                / "production-monitor.yml"
            ).read_text(encoding="utf-8"),
            "django_workflow_text": (
                PROJECT_ROOT / ".github" / "workflows" / "django-ci.yml"
            ).read_text(encoding="utf-8"),
            "bootstrap_text": (
                PROJECT_ROOT
                / "ops"
                / "provision"
                / "ubuntu-bootstrap.sh"
            ).read_text(encoding="utf-8"),
            "host_docs_text": (
                PROJECT_ROOT / "docs" / "HOST_PROVISIONING.md"
            ).read_text(encoding="utf-8"),
        }

    def test_production_monitor_schedule_without_timer_is_rejected(self):
        inputs = self.production_monitor_schedule_inputs()
        inputs["monitor_timer_text"] = inputs["monitor_timer_text"].replace(
            "Persistent=true",
            "Persistent=false",
            1,
        )

        findings = capacity.validate_production_monitor_schedule(**inputs)

        self.assertIn(
            (
                "vapes-shop-production-monitor.timer no contiene "
                "Persistent=true"
            ),
            findings,
        )

    def test_production_monitor_schedule_without_env_file_is_rejected(self):
        inputs = self.production_monitor_schedule_inputs()
        inputs["monitor_service_text"] = inputs[
            "monitor_service_text"
        ].replace(
            "EnvironmentFile=/etc/vapes-shop/production-monitor.env",
            "EnvironmentFile=/etc/vapes-shop/unsafe-monitor.env",
            1,
        )

        findings = capacity.validate_production_monitor_schedule(**inputs)

        self.assertIn(
            (
                "vapes-shop-production-monitor.service no contiene "
                "EnvironmentFile=/etc/vapes-shop/production-monitor.env"
            ),
            findings,
        )

    def test_production_monitor_schedule_without_artifact_is_rejected(self):
        inputs = self.production_monitor_schedule_inputs()
        inputs["monitor_workflow_text"] = inputs[
            "monitor_workflow_text"
        ].replace(
            "--output monitor-results/production-monitor.json",
            "--output /tmp/ephemeral-monitor.json",
            1,
        )

        findings = capacity.validate_production_monitor_schedule(**inputs)

        self.assertIn(
            (
                "production-monitor.yml no contiene "
                "--output monitor-results/production-monitor.json"
            ),
            findings,
        )

    def test_backup_monitor_without_root_symlink_guard_is_rejected(self):
        monitor_text = (
            PROJECT_ROOT / "scripts" / "monitor_backups.py"
        ).read_text(encoding="utf-8")
        invalid_text = monitor_text.replace(
            "root.parent.is_symlink()",
            "False",
            1,
        )

        findings = capacity.validate_backup_monitor(invalid_text)

        self.assertIn(
            "scripts/monitor_backups.py no contiene root.parent.is_symlink()",
            findings,
        )

    def test_backup_monitor_config_without_read_only_mount_is_rejected(self):
        compose_text = (PROJECT_ROOT / "compose.yaml").read_text(
            encoding="utf-8"
        )
        production_compose_text = (
            PROJECT_ROOT / "compose.production.yaml"
        ).read_text(encoding="utf-8")
        local_env_text = (
            PROJECT_ROOT / "compose.env.example"
        ).read_text(encoding="utf-8")
        production_env_text = (
            PROJECT_ROOT / "compose.production.env.example"
        ).read_text(encoding="utf-8")
        workflow_text = (
            PROJECT_ROOT / ".github" / "workflows" / "django-ci.yml"
        ).read_text(encoding="utf-8")
        deploy_text = (
            PROJECT_ROOT / "scripts" / "deploy_production.py"
        ).read_text(encoding="utf-8")
        invalid_compose = compose_text.replace(
            "${BACKUP_PATH:-./backups}:/backups:ro",
            "${BACKUP_PATH:-./backups}:/backups",
        )

        findings = capacity.validate_backup_monitor_config(
            invalid_compose,
            production_compose_text,
            local_env_text,
            production_env_text,
            workflow_text,
            deploy_text,
        )

        self.assertIn(
            (
                "compose.yaml no contiene "
                "${BACKUP_PATH:-./backups}:/backups:ro"
            ),
            findings,
        )

    def test_backup_monitor_config_without_age_threshold_is_rejected(self):
        compose_text = (PROJECT_ROOT / "compose.yaml").read_text(
            encoding="utf-8"
        )
        production_compose_text = (
            PROJECT_ROOT / "compose.production.yaml"
        ).read_text(encoding="utf-8")
        local_env_text = (
            PROJECT_ROOT / "compose.env.example"
        ).read_text(encoding="utf-8")
        production_env_text = (
            PROJECT_ROOT / "compose.production.env.example"
        ).read_text(encoding="utf-8")
        workflow_text = (
            PROJECT_ROOT / ".github" / "workflows" / "django-ci.yml"
        ).read_text(encoding="utf-8")
        deploy_text = (
            PROJECT_ROOT / "scripts" / "deploy_production.py"
        ).read_text(encoding="utf-8")
        invalid_env = local_env_text.replace(
            "BACKUP_MAX_AGE_HOURS=26\n",
            "",
            1,
        )

        findings = capacity.validate_backup_monitor_config(
            compose_text,
            production_compose_text,
            invalid_env,
            production_env_text,
            workflow_text,
            deploy_text,
        )

        self.assertIn(
            "compose.env.example no define BACKUP_MAX_AGE_HOURS",
            findings,
        )

    def test_external_backup_without_restore_comparison_is_rejected(self):
        script_text = (
            PROJECT_ROOT / "scripts" / "external_backup.py"
        ).read_text(encoding="utf-8")
        invalid_text = script_text.replace(
            "compare_files",
            "restore_not_compared",
        )

        findings = capacity.validate_external_backup_script(invalid_text)

        self.assertIn(
            "scripts/external_backup.py no contiene compare_files",
            findings,
        )

    def test_external_backup_without_report_symlink_guard_is_rejected(self):
        script_text = (
            PROJECT_ROOT / "scripts" / "external_backup.py"
        ).read_text(encoding="utf-8")
        invalid_text = script_text.replace(
            "temporary_path.is_symlink()",
            "False",
            1,
        )

        findings = capacity.validate_external_backup_script(invalid_text)

        self.assertIn(
            (
                "scripts/external_backup.py no contiene "
                "temporary_path.is_symlink()"
            ),
            findings,
        )

    def test_external_backup_without_directory_guards_is_rejected(self):
        script_text = (
            PROJECT_ROOT / "scripts" / "external_backup.py"
        ).read_text(encoding="utf-8")
        invalid_text = script_text.replace(
            "backup_root.exists() and not backup_root.is_dir()",
            "False",
            1,
        )

        findings = capacity.validate_external_backup_script(invalid_text)

        self.assertIn(
            (
                "scripts/external_backup.py no contiene "
                "backup_root.exists() and not backup_root.is_dir()"
            ),
            findings,
        )

        invalid_text = script_text.replace(
            "restore_parent.exists() and not restore_parent.is_dir()",
            "False",
            1,
        )

        findings = capacity.validate_external_backup_script(invalid_text)

        self.assertIn(
            (
                "scripts/external_backup.py no contiene "
                "restore_parent.exists() and not restore_parent.is_dir()"
            ),
            findings,
        )

    def test_external_backup_config_without_pinned_checksum_is_rejected(self):
        backup_dockerfile_text = (
            PROJECT_ROOT / "docker" / "backup.Dockerfile"
        ).read_text(encoding="utf-8")
        compose_text = (PROJECT_ROOT / "compose.yaml").read_text(
            encoding="utf-8"
        )
        production_compose_text = (
            PROJECT_ROOT / "compose.production.yaml"
        ).read_text(encoding="utf-8")
        local_env_text = (
            PROJECT_ROOT / "compose.env.example"
        ).read_text(encoding="utf-8")
        production_env_text = (
            PROJECT_ROOT / "compose.production.env.example"
        ).read_text(encoding="utf-8")
        workflow_text = (
            PROJECT_ROOT / ".github" / "workflows" / "django-ci.yml"
        ).read_text(encoding="utf-8")
        deploy_text = (
            PROJECT_ROOT / "scripts" / "deploy_production.py"
        ).read_text(encoding="utf-8")
        invalid_dockerfile = backup_dockerfile_text.replace(
            "sha256sum --check --strict",
            "true",
            1,
        )

        findings = capacity.validate_external_backup_config(
            invalid_dockerfile,
            compose_text,
            production_compose_text,
            local_env_text,
            production_env_text,
            workflow_text,
            deploy_text,
        )

        self.assertIn(
            (
                "docker/backup.Dockerfile no contiene "
                "sha256sum --check --strict"
            ),
            findings,
        )

    def test_external_backup_config_without_restore_ci_is_rejected(self):
        backup_dockerfile_text = (
            PROJECT_ROOT / "docker" / "backup.Dockerfile"
        ).read_text(encoding="utf-8")
        compose_text = (PROJECT_ROOT / "compose.yaml").read_text(
            encoding="utf-8"
        )
        production_compose_text = (
            PROJECT_ROOT / "compose.production.yaml"
        ).read_text(encoding="utf-8")
        local_env_text = (
            PROJECT_ROOT / "compose.env.example"
        ).read_text(encoding="utf-8")
        production_env_text = (
            PROJECT_ROOT / "compose.production.env.example"
        ).read_text(encoding="utf-8")
        workflow_text = (
            PROJECT_ROOT / ".github" / "workflows" / "django-ci.yml"
        ).read_text(encoding="utf-8")
        deploy_text = (
            PROJECT_ROOT / "scripts" / "deploy_production.py"
        ).read_text(encoding="utf-8")
        invalid_workflow = workflow_text.replace(
            "external-restore-verification.json",
            "external-copy-only.json",
        )

        findings = capacity.validate_external_backup_config(
            backup_dockerfile_text,
            compose_text,
            production_compose_text,
            local_env_text,
            production_env_text,
            invalid_workflow,
            deploy_text,
        )

        self.assertIn(
            (
                "django-ci.yml no contiene "
                "external-restore-verification.json"
            ),
            findings,
        )

    def disaster_recovery_inputs(self):
        return {
            "recovery_text": (
                PROJECT_ROOT / "scripts" / "recover_production.py"
            ).read_text(encoding="utf-8"),
            "external_backup_text": (
                PROJECT_ROOT / "scripts" / "external_backup.py"
            ).read_text(encoding="utf-8"),
            "deploy_text": (
                PROJECT_ROOT / "scripts" / "deploy_production.py"
            ).read_text(encoding="utf-8"),
            "compose_text": (
                PROJECT_ROOT / "compose.yaml"
            ).read_text(encoding="utf-8"),
            "production_compose_text": (
                PROJECT_ROOT / "compose.production.yaml"
            ).read_text(encoding="utf-8"),
            "local_env_text": (
                PROJECT_ROOT / "compose.env.example"
            ).read_text(encoding="utf-8"),
            "production_env_text": (
                PROJECT_ROOT / "compose.production.env.example"
            ).read_text(encoding="utf-8"),
            "django_workflow_text": (
                PROJECT_ROOT / ".github" / "workflows" / "django-ci.yml"
            ).read_text(encoding="utf-8"),
            "disaster_docs_text": (
                PROJECT_ROOT / "docs" / "DISASTER_RECOVERY.md"
            ).read_text(encoding="utf-8"),
        }

    def test_disaster_recovery_without_volume_guard_is_rejected(self):
        inputs = self.disaster_recovery_inputs()
        inputs["recovery_text"] = inputs["recovery_text"].replace(
            "label=com.docker.compose.project=vapes-shop",
            "label=missing",
            1,
        )

        findings = capacity.validate_disaster_recovery(**inputs)

        self.assertIn(
            (
                "recover_production.py no contiene "
                "label=com.docker.compose.project=vapes-shop"
            ),
            findings,
        )

    def test_disaster_recovery_without_rto_env_is_rejected(self):
        inputs = self.disaster_recovery_inputs()
        inputs["production_env_text"] = inputs[
            "production_env_text"
        ].replace(
            "DISASTER_RECOVERY_RTO_SECONDS=1800\n",
            "",
            1,
        )

        findings = capacity.validate_disaster_recovery(**inputs)

        self.assertIn(
            (
                "compose.production.env.example no define "
                "DISASTER_RECOVERY_RTO_SECONDS"
            ),
            findings,
        )

    def test_recovery_state_parent_symlink_guard_is_rejected(self):
        inputs = self.disaster_recovery_inputs()
        inputs["recovery_text"] = inputs["recovery_text"].replace(
            "current_state_path.parent.is_symlink()",
            "False",
            1,
        )

        findings = capacity.validate_disaster_recovery(**inputs)

        self.assertIn(
            (
                "recover_production.py no contiene "
                "current_state_path.parent.is_symlink()"
            ),
            findings,
        )

    def test_recovery_state_directory_symlink_guard_is_rejected(self):
        inputs = self.disaster_recovery_inputs()
        inputs["recovery_text"] = inputs["recovery_text"].replace(
            "state_directory_path.parent.is_symlink()",
            "False",
            1,
        )

        findings = capacity.validate_disaster_recovery(**inputs)

        self.assertIn(
            (
                "recover_production.py no contiene "
                "state_directory_path.parent.is_symlink()"
            ),
            findings,
        )

    def test_recovery_output_report_without_temporary_guard_is_rejected(
        self,
    ):
        inputs = self.disaster_recovery_inputs()
        inputs["recovery_text"] = inputs["recovery_text"].replace(
            "    if temporary_path.is_symlink():",
            "    if False:",
            1,
        )

        findings = capacity.validate_disaster_recovery(**inputs)

        self.assertIn(
            (
                "recover_production.py no contiene 4 validaciones "
                "temporary_path.is_symlink()"
            ),
            findings,
        )

    def test_external_recovery_without_latest_guard_is_rejected(self):
        inputs = self.disaster_recovery_inputs()
        inputs["external_backup_text"] = inputs[
            "external_backup_text"
        ].replace(
            "temporary_latest.is_symlink()",
            "False",
            1,
        )

        findings = capacity.validate_disaster_recovery(**inputs)

        self.assertIn(
            "external_backup.py no contiene temporary_latest.is_symlink()",
            findings,
        )

    def release_manifest_inputs(self):
        return {
            "manifest_text": (
                PROJECT_ROOT / "scripts" / "release_manifest.py"
            ).read_text(encoding="utf-8"),
            "fetch_text": (
                PROJECT_ROOT / "scripts" / "fetch_release_manifest.py"
            ).read_text(encoding="utf-8"),
            "recovery_text": (
                PROJECT_ROOT / "scripts" / "recover_production.py"
            ).read_text(encoding="utf-8"),
            "publish_workflow_text": (
                PROJECT_ROOT
                / ".github"
                / "workflows"
                / "publish-images.yml"
            ).read_text(encoding="utf-8"),
            "disaster_docs_text": (
                PROJECT_ROOT / "docs" / "DISASTER_RECOVERY.md"
            ).read_text(encoding="utf-8"),
            "bootstrap_text": (
                PROJECT_ROOT
                / "ops"
                / "provision"
                / "ubuntu-bootstrap.sh"
            ).read_text(encoding="utf-8"),
            "readiness_text": (
                PROJECT_ROOT / "scripts" / "check_host_readiness.py"
            ).read_text(encoding="utf-8"),
        }

    def test_release_manifest_without_attestation_is_rejected(self):
        inputs = self.release_manifest_inputs()
        inputs["publish_workflow_text"] = inputs[
            "publish_workflow_text"
        ].replace(
            "subject-path: recovery-manifest.json",
            "subject-path: untrusted.txt",
            1,
        )

        findings = capacity.validate_release_manifest(**inputs)

        self.assertIn(
            (
                "publish-images.yml no contiene "
                "subject-path: recovery-manifest.json"
            ),
            findings,
        )

    def test_release_manifest_cannot_be_overwritten(self):
        inputs = self.release_manifest_inputs()
        inputs["publish_workflow_text"] += "\n--clobber\n"

        findings = capacity.validate_release_manifest(**inputs)

        self.assertIn(
            "publish-images.yml no debe reemplazar manifiestos publicados",
            findings,
        )

    def test_release_manifest_without_temporary_guard_is_rejected(self):
        inputs = self.release_manifest_inputs()
        inputs["manifest_text"] = inputs["manifest_text"].replace(
            "temporary_path.is_symlink()",
            "False",
            1,
        )

        findings = capacity.validate_release_manifest(**inputs)

        self.assertIn(
            (
                "release_manifest.py debe validar temporales simbolicos "
                "en manifiesto y checksum"
            ),
            findings,
        )

    def test_release_manifest_without_directory_guard_is_rejected(self):
        inputs = self.release_manifest_inputs()
        inputs["manifest_text"] = inputs["manifest_text"].replace(
            "path.exists() and path.is_dir()",
            "False",
            1,
        )

        findings = capacity.validate_release_manifest(**inputs)

        self.assertIn(
            (
                "release_manifest.py debe rechazar destinos directorio "
                "en manifiesto y checksum"
            ),
            findings,
        )

    def test_release_fetch_without_attestation_is_rejected(self):
        inputs = self.release_manifest_inputs()
        inputs["fetch_text"] = inputs["fetch_text"].replace(
            '"attestation",',
            '"unverified",',
            1,
        )

        findings = capacity.validate_release_manifest(**inputs)

        self.assertIn(
            "fetch_release_manifest.py no contiene attestation",
            findings,
        )

    def test_release_fetch_without_regular_directory_guard_is_rejected(self):
        inputs = self.release_manifest_inputs()
        inputs["fetch_text"] = inputs["fetch_text"].replace(
            "output_directory.exists() and not output_directory.is_dir()",
            "False",
            1,
        )

        findings = capacity.validate_release_manifest(**inputs)

        self.assertIn(
            (
                "fetch_release_manifest.py no contiene "
                "output_directory.exists() and not output_directory.is_dir()"
            ),
            findings,
        )

    def test_backup_operations_without_shared_lock_is_rejected(self):
        script_text = (
            PROJECT_ROOT / "scripts" / "backup_operations.py"
        ).read_text(encoding="utf-8")
        invalid_text = script_text.replace(
            "self.state_directory.with_name",
            "Path",
            1,
        )

        findings = capacity.validate_backup_operations(invalid_text)

        self.assertIn(
            (
                "scripts/backup_operations.py no contiene "
                "self.state_directory.with_name"
            ),
            findings,
        )

    def test_backup_operations_without_state_directory_guard_is_rejected(
        self,
    ):
        script_text = (
            PROJECT_ROOT / "scripts" / "backup_operations.py"
        ).read_text(encoding="utf-8")
        invalid_text = script_text.replace(
            "state_directory_path.parent.is_symlink()",
            "False",
            1,
        )

        findings = capacity.validate_backup_operations(invalid_text)

        self.assertIn(
            (
                "scripts/backup_operations.py no contiene "
                "state_directory_path.parent.is_symlink()"
            ),
            findings,
        )

    def test_backup_operations_without_report_symlink_guard_is_rejected(self):
        script_text = (
            PROJECT_ROOT / "scripts" / "backup_operations.py"
        ).read_text(encoding="utf-8")
        invalid_text = script_text.replace(
            "temporary_path.is_symlink()",
            "False",
            1,
        )

        findings = capacity.validate_backup_operations(invalid_text)

        self.assertIn(
            (
                "scripts/backup_operations.py no contiene "
                "temporary_path.is_symlink()"
            ),
            findings,
        )

    def test_backup_schedule_without_persistent_timer_is_rejected(self):
        local_env_text = (
            PROJECT_ROOT / "compose.env.example"
        ).read_text(encoding="utf-8")
        production_env_text = (
            PROJECT_ROOT / "compose.production.env.example"
        ).read_text(encoding="utf-8")
        workflow_text = (
            PROJECT_ROOT / ".github" / "workflows" / "django-ci.yml"
        ).read_text(encoding="utf-8")
        systemd_root = PROJECT_ROOT / "ops" / "systemd"
        backup_service_text = (
            systemd_root / "vapes-shop-backup.service"
        ).read_text(encoding="utf-8")
        backup_timer_text = (
            systemd_root / "vapes-shop-backup.timer"
        ).read_text(encoding="utf-8")
        drill_service_text = (
            systemd_root / "vapes-shop-recovery-drill.service"
        ).read_text(encoding="utf-8")
        drill_timer_text = (
            systemd_root / "vapes-shop-recovery-drill.timer"
        ).read_text(encoding="utf-8")
        schedule_env_text = (
            systemd_root / "backup-operations.env.example"
        ).read_text(encoding="utf-8")
        invalid_timer = backup_timer_text.replace(
            "Persistent=true",
            "Persistent=false",
            1,
        )

        findings = capacity.validate_backup_schedule(
            local_env_text,
            production_env_text,
            workflow_text,
            backup_service_text,
            invalid_timer,
            drill_service_text,
            drill_timer_text,
            schedule_env_text,
        )

        self.assertIn(
            "vapes-shop-backup.timer no contiene Persistent=true",
            findings,
        )

    def test_backup_schedule_without_rto_objective_is_rejected(self):
        local_env_text = (
            PROJECT_ROOT / "compose.env.example"
        ).read_text(encoding="utf-8")
        production_env_text = (
            PROJECT_ROOT / "compose.production.env.example"
        ).read_text(encoding="utf-8")
        workflow_text = (
            PROJECT_ROOT / ".github" / "workflows" / "django-ci.yml"
        ).read_text(encoding="utf-8")
        systemd_root = PROJECT_ROOT / "ops" / "systemd"
        backup_service_text = (
            systemd_root / "vapes-shop-backup.service"
        ).read_text(encoding="utf-8")
        backup_timer_text = (
            systemd_root / "vapes-shop-backup.timer"
        ).read_text(encoding="utf-8")
        drill_service_text = (
            systemd_root / "vapes-shop-recovery-drill.service"
        ).read_text(encoding="utf-8")
        drill_timer_text = (
            systemd_root / "vapes-shop-recovery-drill.timer"
        ).read_text(encoding="utf-8")
        schedule_env_text = (
            systemd_root / "backup-operations.env.example"
        ).read_text(encoding="utf-8")
        invalid_schedule_env = schedule_env_text.replace(
            "BACKUP_RTO_SECONDS=900\n",
            "",
            1,
        )

        findings = capacity.validate_backup_schedule(
            local_env_text,
            production_env_text,
            workflow_text,
            backup_service_text,
            backup_timer_text,
            drill_service_text,
            drill_timer_text,
            invalid_schedule_env,
        )

        self.assertIn(
            (
                "backup-operations.env.example no define "
                "BACKUP_RTO_SECONDS"
            ),
            findings,
        )

    def host_provisioning_inputs(self):
        return {
            "bootstrap_text": (
                PROJECT_ROOT
                / "ops"
                / "provision"
                / "ubuntu-bootstrap.sh"
            ).read_text(encoding="utf-8"),
            "readiness_text": (
                PROJECT_ROOT / "scripts" / "check_host_readiness.py"
            ).read_text(encoding="utf-8"),
            "deploy_text": (
                PROJECT_ROOT / "scripts" / "deploy_production.py"
            ).read_text(encoding="utf-8"),
            "compose_text": (
                PROJECT_ROOT / "compose.yaml"
            ).read_text(encoding="utf-8"),
            "local_env_text": (
                PROJECT_ROOT / "compose.env.example"
            ).read_text(encoding="utf-8"),
            "production_env_text": (
                PROJECT_ROOT / "compose.production.env.example"
            ).read_text(encoding="utf-8"),
            "django_workflow_text": (
                PROJECT_ROOT / ".github" / "workflows" / "django-ci.yml"
            ).read_text(encoding="utf-8"),
        }

    def test_host_bootstrap_without_default_deny_is_rejected(self):
        inputs = self.host_provisioning_inputs()
        inputs["bootstrap_text"] = inputs["bootstrap_text"].replace(
            "ufw default deny incoming",
            "ufw default allow incoming",
            1,
        )

        findings = capacity.validate_host_provisioning(**inputs)

        self.assertIn(
            "ubuntu-bootstrap.sh no contiene ufw default deny incoming",
            findings,
        )

    def test_production_host_exposed_on_all_interfaces_is_rejected(self):
        inputs = self.host_provisioning_inputs()
        inputs["production_env_text"] = inputs[
            "production_env_text"
        ].replace(
            "APP_BIND_ADDRESS=127.0.0.1",
            "APP_BIND_ADDRESS=0.0.0.0",
            1,
        )

        findings = capacity.validate_host_provisioning(**inputs)

        self.assertIn(
            "compose.production.env.example no limita APP_BIND_ADDRESS",
            findings,
        )

    def test_deployment_state_parent_symlink_guard_is_rejected(self):
        inputs = self.host_provisioning_inputs()
        inputs["deploy_text"] = inputs["deploy_text"].replace(
            "path.parent.is_symlink()",
            "False",
            1,
        )

        findings = capacity.validate_host_provisioning(**inputs)

        self.assertIn(
            "deploy_production.py no restringe los archivos de estado",
            findings,
        )

    def test_deployment_state_directory_symlink_guard_is_rejected(self):
        inputs = self.host_provisioning_inputs()
        inputs["deploy_text"] = inputs["deploy_text"].replace(
            "state_directory_path.parent.is_symlink()",
            "False",
            1,
        )

        findings = capacity.validate_host_provisioning(**inputs)

        self.assertIn(
            "deploy_production.py no restringe los archivos de estado",
            findings,
        )

    def test_host_readiness_without_report_temporary_guard_is_rejected(self):
        inputs = self.host_provisioning_inputs()
        inputs["readiness_text"] = inputs["readiness_text"].replace(
            "temporary_path.is_symlink()",
            "False",
            1,
        )

        findings = capacity.validate_host_provisioning(**inputs)

        self.assertIn(
            "check_host_readiness.py no contiene temporary_path.is_symlink()",
            findings,
        )


if __name__ == "__main__":
    unittest.main()
