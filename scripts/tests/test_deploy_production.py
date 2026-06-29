import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "deploy_production.py"
SPEC = importlib.util.spec_from_file_location("deploy_production", SCRIPT_PATH)
deploy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deploy)


APP_V1 = f"ghcr.io/example/vapes-shop@sha256:{'1' * 64}"
APP_V2 = f"ghcr.io/example/vapes-shop@sha256:{'2' * 64}"
BACKUP_V1 = f"ghcr.io/example/vapes-shop-backup@sha256:{'3' * 64}"
BACKUP_V2 = f"ghcr.io/example/vapes-shop-backup@sha256:{'4' * 64}"


class FakeRunner:
    def __init__(self, fail_predicate=None):
        self.calls = []
        self.fail_predicate = fail_predicate

    def run(self, command, env):
        call = {
            "command": command,
            "app_image": env["APP_IMAGE"],
            "backup_image": env["BACKUP_IMAGE"],
        }
        self.calls.append(call)

        if self.fail_predicate and self.fail_predicate(call):
            raise deploy.DeploymentError("fallo simulado")


class DeploymentControllerTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        (self.root / "compose.yaml").write_text(
            "services: {}\n",
            encoding="utf-8",
        )
        (self.root / "compose.production.yaml").write_text(
            "services: {}\n",
            encoding="utf-8",
        )
        (self.root / "compose.env").write_text(
            (
                "DJANGO_SECRET_KEY=test\n"
                "DJANGO_ALLOWED_HOSTS=shop.example\n"
            ),
            encoding="utf-8",
        )
        self.state_directory = self.root / ".deploy"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def build_controller(self, runner):
        return deploy.DeploymentController(
            project_root=self.root,
            env_file=self.root / "compose.env",
            state_directory=self.state_directory,
            runner=runner,
            wait_timeout=30,
        )

    def test_state_directory_symlink_is_rejected_before_lock(self):
        runner = FakeRunner()

        def is_symlink(path):
            return path == self.state_directory

        with mock.patch.object(deploy.Path, "is_symlink", is_symlink):
            with self.assertRaisesRegex(
                deploy.DeploymentError,
                (
                    "directorio de estado de despliegue no admite "
                    "enlaces simbolicos"
                ),
            ):
                self.build_controller(runner)

        self.assertEqual(runner.calls, [])
        self.assertFalse(
            self.state_directory.with_name(".deploy.lock").exists()
        )

    def test_state_files_are_written_with_restricted_permissions(self):
        controller = self.build_controller(FakeRunner())
        state_path = self.state_directory / "current.json"

        with mock.patch.object(deploy.os, "chmod") as chmod:
            controller.write_state(
                state_path,
                {
                    "app_image": APP_V1,
                    "backup_image": BACKUP_V1,
                },
            )

        chmod.assert_called_once_with(
            state_path.with_suffix(".tmp"),
            0o600,
        )

    def test_state_symlink_is_rejected_before_write(self):
        controller = self.build_controller(FakeRunner())
        state_path = self.state_directory / "current.json"

        def is_symlink(path):
            return path == state_path

        with mock.patch.object(deploy.Path, "is_symlink", is_symlink):
            with self.assertRaisesRegex(
                deploy.DeploymentError,
                "estado de despliegue no admite enlaces simbolicos",
            ):
                controller.write_state(
                    state_path,
                    {
                        "app_image": APP_V1,
                        "backup_image": BACKUP_V1,
                    },
                )

        self.assertFalse(state_path.exists())

    def test_temporary_state_symlink_is_rejected_before_write(self):
        controller = self.build_controller(FakeRunner())
        state_path = self.state_directory / "current.json"
        temporary_path = state_path.with_suffix(".tmp")

        def is_symlink(path):
            return path == temporary_path

        with mock.patch.object(deploy.Path, "is_symlink", is_symlink):
            with self.assertRaisesRegex(
                deploy.DeploymentError,
                "estado de despliegue no admite enlaces simbolicos",
            ):
                controller.write_state(
                    state_path,
                    {
                        "app_image": APP_V1,
                        "backup_image": BACKUP_V1,
                    },
                )

        self.assertFalse(state_path.exists())

    def test_state_parent_symlink_is_rejected_before_write(self):
        controller = self.build_controller(FakeRunner())
        state_path = self.state_directory / "current.json"

        def is_symlink(path):
            return path == state_path.parent

        with mock.patch.object(deploy.Path, "is_symlink", is_symlink):
            with self.assertRaisesRegex(
                deploy.DeploymentError,
                "estado de despliegue no admite enlaces simbolicos",
            ):
                controller.write_state(
                    state_path,
                    {
                        "app_image": APP_V1,
                        "backup_image": BACKUP_V1,
                    },
                )

        self.assertFalse(state_path.exists())

    def write_current_state(self):
        self.state_directory.mkdir()
        (self.state_directory / "current.json").write_text(
            json.dumps(
                {
                    "app_image": APP_V1,
                    "backup_image": BACKUP_V1,
                    "deployed_at": "2026-01-01T00:00:00Z",
                }
            ),
            encoding="utf-8",
        )

    def test_deploy_runs_backup_migration_and_updates_state(self):
        runner = FakeRunner()
        controller = self.build_controller(runner)

        result = controller.deploy(APP_V2, BACKUP_V2)

        self.assertEqual(result["status"], "deployed")
        current = json.loads(
            (self.state_directory / "current.json").read_text(
                encoding="utf-8",
            )
        )
        self.assertEqual(current["app_image"], APP_V2)
        commands = [" ".join(call["command"]) for call in runner.calls]
        self.assertTrue(
            any(
                " run --rm --no-deps backup" in cmd
                for cmd in commands
            )
        )
        self.assertTrue(
            any(
                " run --rm --no-deps backup-monitor" in cmd
                for cmd in commands
            )
        )
        self.assertTrue(
            any(
                " run --rm --no-deps external-backup backup" in cmd
                for cmd in commands
            )
        )
        self.assertTrue(any(" check --deploy" in cmd for cmd in commands))
        self.assertTrue(any(" production_check" in cmd for cmd in commands))
        self.assertTrue(
            any(
                " run --rm --no-deps migrate" in cmd
                for cmd in commands
            )
        )
        self.assertTrue(any(" exec --no-tty proxy wget" in cmd for cmd in commands))
        health_command = next(
            command
            for command in commands
            if " exec --no-tty proxy wget" in command
        )
        self.assertIn("Host: shop.example", health_command)
        self.assertIn("X-Forwarded-Proto: https", health_command)
        production_check_index = next(
            index
            for index, command in enumerate(commands)
            if " production_check" in command
        )
        backup_index = next(
            index
            for index, command in enumerate(commands)
            if " run --rm --no-deps backup" in command
        )
        backup_monitor_index = next(
            index
            for index, command in enumerate(commands)
            if " run --rm --no-deps backup-monitor" in command
        )
        external_backup_index = next(
            index
            for index, command in enumerate(commands)
            if " run --rm --no-deps external-backup backup" in command
        )
        migration_index = next(
            index
            for index, command in enumerate(commands)
            if command.endswith(" run --rm --no-deps migrate")
        )
        self.assertLess(production_check_index, backup_index)
        self.assertLess(backup_index, backup_monitor_index)
        self.assertLess(backup_monitor_index, external_backup_index)
        self.assertLess(external_backup_index, migration_index)

    def test_validation_failure_stops_before_database_and_backup(self):
        def fail_validation(call):
            return " production_check" in " ".join(call["command"])

        runner = FakeRunner(fail_predicate=fail_validation)
        controller = self.build_controller(runner)

        with self.assertRaises(deploy.DeploymentError):
            controller.deploy(APP_V2, BACKUP_V2)

        commands = [" ".join(call["command"]) for call in runner.calls]
        self.assertFalse(
            any(" up --detach --wait " in command for command in commands)
        )
        self.assertFalse(
            any(" run --rm --no-deps backup" in command for command in commands)
        )

    def test_failed_new_application_rolls_back_previous_image(self):
        self.write_current_state()
        failures = {"pending": True}

        def fail_new_web(call):
            command = " ".join(call["command"])

            if (
                failures["pending"]
                and call["app_image"] == APP_V2
                and " up --detach --no-build " in command
            ):
                failures["pending"] = False
                return True

            return False

        runner = FakeRunner(fail_predicate=fail_new_web)
        controller = self.build_controller(runner)

        with self.assertRaises(deploy.DeploymentError):
            controller.deploy(APP_V2, BACKUP_V2)

        rollback_calls = [
            call
            for call in runner.calls
            if call["app_image"] == APP_V1
        ]
        self.assertTrue(rollback_calls)
        current = json.loads(
            (self.state_directory / "current.json").read_text(
                encoding="utf-8",
            )
        )
        self.assertEqual(current["app_image"], APP_V1)

    def test_backup_failure_stops_before_migration(self):
        def fail_backup(call):
            return " run --rm --no-deps backup" in " ".join(call["command"])

        runner = FakeRunner(fail_predicate=fail_backup)
        controller = self.build_controller(runner)

        with self.assertRaises(deploy.DeploymentError):
            controller.deploy(APP_V2, BACKUP_V2)

        commands = [" ".join(call["command"]) for call in runner.calls]
        self.assertFalse(
            any(
                command.endswith(" run --rm --no-deps migrate")
                for command in commands
            )
        )

    def test_backup_monitor_failure_stops_before_migration(self):
        def fail_backup_monitor(call):
            return (
                " run --rm --no-deps backup-monitor"
                in " ".join(call["command"])
            )

        runner = FakeRunner(fail_predicate=fail_backup_monitor)
        controller = self.build_controller(runner)

        with self.assertRaises(deploy.DeploymentError):
            controller.deploy(APP_V2, BACKUP_V2)

        commands = [" ".join(call["command"]) for call in runner.calls]
        self.assertTrue(
            any(
                " run --rm --no-deps backup" in command
                for command in commands
            )
        )
        self.assertFalse(
            any(
                command.endswith(" run --rm --no-deps migrate")
                for command in commands
            )
        )

    def test_external_backup_failure_stops_before_migration(self):
        def fail_external_backup(call):
            return (
                " run --rm --no-deps external-backup backup"
                in " ".join(call["command"])
            )

        runner = FakeRunner(fail_predicate=fail_external_backup)
        controller = self.build_controller(runner)

        with self.assertRaises(deploy.DeploymentError):
            controller.deploy(APP_V2, BACKUP_V2)

        commands = [" ".join(call["command"]) for call in runner.calls]
        self.assertTrue(
            any(
                " run --rm --no-deps backup-monitor" in command
                for command in commands
            )
        )
        self.assertFalse(
            any(
                command.endswith(" run --rm --no-deps migrate")
                for command in commands
            )
        )

    def test_manual_rollback_swaps_current_and_previous(self):
        self.write_current_state()
        (self.state_directory / "previous.json").write_text(
            json.dumps(
                {
                    "app_image": APP_V2,
                    "backup_image": BACKUP_V2,
                    "deployed_at": "2025-12-01T00:00:00Z",
                }
            ),
            encoding="utf-8",
        )
        runner = FakeRunner()
        controller = self.build_controller(runner)

        result = controller.rollback()

        self.assertEqual(result["status"], "rolled_back")
        current = json.loads(
            (self.state_directory / "current.json").read_text(
                encoding="utf-8",
            )
        )
        previous = json.loads(
            (self.state_directory / "previous.json").read_text(
                encoding="utf-8",
            )
        )
        self.assertEqual(current["app_image"], APP_V2)
        self.assertEqual(previous["app_image"], APP_V1)
        commands = [" ".join(call["command"]) for call in runner.calls]
        self.assertFalse(
            any(
                command.endswith(" run --rm --no-deps migrate")
                for command in commands
            )
        )

    def test_mutable_image_reference_is_rejected(self):
        runner = FakeRunner()
        controller = self.build_controller(runner)

        with self.assertRaises(deploy.DeploymentError):
            controller.deploy(
                "ghcr.io/example/vapes-shop:latest",
                BACKUP_V2,
            )

        self.assertEqual(runner.calls, [])


if __name__ == "__main__":
    unittest.main()
