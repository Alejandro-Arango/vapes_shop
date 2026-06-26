import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "check_host_readiness.py"
)
SPEC = importlib.util.spec_from_file_location("check_host_readiness", SCRIPT_PATH)
readiness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(readiness)


class FakeRunner:
    def __init__(self, responses):
        self.responses = responses

    def run(self, command):
        return self.responses.get(tuple(command), (False, "missing"))


class HostReadinessTests(unittest.TestCase):
    def test_supported_ubuntu_release_is_accepted(self):
        findings = readiness.validate_ubuntu_release(
            {
                "ID": "ubuntu",
                "VERSION_ID": "24.04",
                "VERSION_CODENAME": "noble",
            }
        )

        self.assertEqual(findings, [])

    def test_unknown_distribution_is_rejected(self):
        findings = readiness.validate_ubuntu_release(
            {
                "ID": "debian",
                "VERSION_ID": "13",
                "VERSION_CODENAME": "trixie",
            }
        )

        self.assertIn("El host no ejecuta Ubuntu.", findings)
        self.assertTrue(
            any("Version de Ubuntu no soportada" in item for item in findings)
        )

    def test_environment_parser_rejects_invalid_key(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env_path = Path(temporary_directory) / "production.env"
            env_path.write_text("invalid-key=value\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                readiness.parse_env_file(env_path)

    def test_production_environment_requires_loopback_binding(self):
        findings = readiness.validate_production_environment(
            {
                "APP_BIND_ADDRESS": "0.0.0.0",
                "BACKUP_PATH": "/srv/vapes-shop/backups",
                "EXTERNAL_BACKUP_ENABLED": "true",
                "BACKUP_REQUIRE_EXTERNAL": "true",
            },
            Path("/srv/vapes-shop"),
        )

        self.assertIn(
            "APP_BIND_ADDRESS debe limitar el proxy a loopback.",
            findings,
        )

    def test_production_environment_requires_external_backup(self):
        findings = readiness.validate_production_environment(
            {
                "APP_BIND_ADDRESS": "127.0.0.1",
                "BACKUP_PATH": "/srv/vapes-shop/backups",
                "EXTERNAL_BACKUP_ENABLED": "false",
                "BACKUP_REQUIRE_EXTERNAL": "false",
            },
            Path("/srv/vapes-shop"),
        )

        self.assertIn("EXTERNAL_BACKUP_ENABLED debe ser true.", findings)
        self.assertIn("BACKUP_REQUIRE_EXTERNAL debe ser true.", findings)

    def test_world_readable_secret_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            secret_path = Path(temporary_directory) / "secret"
            secret_path.write_text("secret", encoding="utf-8")
            os.chmod(secret_path, 0o644)

            findings = readiness.validate_path(
                secret_path,
                expected_uid=None,
                allowed_mode=0o600,
                label="secreto",
            )

        self.assertTrue(any("permisos" in item for item in findings))

    def test_symbolic_link_is_rejected(self):
        if os.name == "nt":
            self.skipTest("Crear symlinks requiere privilegios en Windows.")

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            target = root / "target"
            link = root / "link"
            target.write_text("value", encoding="utf-8")
            link.symlink_to(target)

            findings = readiness.validate_path(
                link,
                expected_uid=None,
                allowed_mode=0o600,
                label="secreto",
            )

        self.assertIn("secreto no puede ser un enlace simbolico.", findings)

    def test_command_check_applies_output_predicate(self):
        runner = FakeRunner(
            {
                ("systemctl", "is-active", "docker.service"): (
                    True,
                    "inactive",
                )
            }
        )

        result = readiness.command_check(
            runner,
            "docker_active",
            ["systemctl", "is-active", "docker.service"],
            lambda value: value == "active",
        )

        self.assertEqual(result["status"], "critical")

    def test_dirty_source_checkout_is_critical(self):
        runner = FakeRunner(
            {
                (
                    "git",
                    "-C",
                    "/srv/vapes-shop",
                    "status",
                    "--porcelain=v1",
                    "--untracked-files=no",
                ): (True, " M compose.yaml"),
            }
        )

        result = readiness.command_check(
            runner,
            "source_clean",
            [
                "git",
                "-C",
                "/srv/vapes-shop",
                "status",
                "--porcelain=v1",
                "--untracked-files=no",
            ],
            lambda value: not value,
        )

        self.assertEqual(result["status"], "critical")

    def test_report_is_written_atomically(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "report.json"
            readiness.write_report(
                output_path,
                {"status": "healthy"},
            )

            self.assertIn(
                '"status": "healthy"',
                output_path.read_text(encoding="utf-8"),
            )
            self.assertFalse(output_path.with_suffix(".json.tmp").exists())

    def test_report_rejects_symbolic_link(self):
        if os.name == "nt":
            self.skipTest("Crear symlinks requiere privilegios en Windows.")

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            target = root / "target.json"
            output_path = root / "report.json"
            target.write_text("{}\n", encoding="utf-8")
            output_path.symlink_to(target)

            with self.assertRaises(ValueError):
                readiness.write_report(
                    output_path,
                    {"status": "healthy"},
                )

    def test_temporary_report_symlink_is_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "report.json"
            temporary_path = output_path.with_suffix(".json.tmp")

            def is_symlink(path):
                return path == temporary_path

            with mock.patch.object(readiness.Path, "is_symlink", is_symlink):
                with self.assertRaisesRegex(
                    ValueError,
                    "reporte no puede reemplazar un enlace simbolico",
                ):
                    readiness.write_report(
                        output_path,
                        {"status": "healthy"},
                    )

            self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
