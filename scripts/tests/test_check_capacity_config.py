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


if __name__ == "__main__":
    unittest.main()
