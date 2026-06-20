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


if __name__ == "__main__":
    unittest.main()
