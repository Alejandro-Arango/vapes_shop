import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "backup_operations.py"
SPEC = importlib.util.spec_from_file_location(
    "backup_operations",
    SCRIPT_PATH,
)
operations = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(operations)


APP_IMAGE = f"ghcr.io/example/vapes-shop@sha256:{'1' * 64}"
BACKUP_IMAGE = f"ghcr.io/example/vapes-shop-backup@sha256:{'2' * 64}"


class FakeRunner:
    def __init__(
        self,
        age_hours=2,
        local_backup_id="20260621T070000Z",
        external_backup_id="20260621T070000Z",
        external_statuses=None,
    ):
        self.age_hours = age_hours
        self.local_backup_id = local_backup_id
        self.external_backup_id = external_backup_id
        self.external_statuses = external_statuses or {
            "backup": "stored_and_restored",
            "verify-latest": "verified",
        }
        self.calls = []

    def run(self, command, environment, timeout):
        self.calls.append(
            {
                "command": command,
                "environment": environment,
                "timeout": timeout,
            }
        )
        joined = " ".join(command)

        if " backup-monitor" in joined:
            return json.dumps(
                {
                    "event": "backup_health",
                    "status": "ok",
                    "backup_id": self.local_backup_id,
                    "age_hours": self.age_hours,
                }
            )

        if " external-backup " in joined:
            action = command[-1]
            return json.dumps(
                {
                    "event": "external_backup",
                    "status": self.external_statuses[action],
                    "backup_id": self.external_backup_id,
                    "snapshot_id": "a" * 64,
                }
            )

        return ""


class BackupOperationsTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temporary_directory.name)
        (self.project_root / "compose.yaml").write_text(
            "services: {}\n",
            encoding="utf-8",
        )
        (self.project_root / "compose.production.yaml").write_text(
            "services: {}\n",
            encoding="utf-8",
        )
        self.env_file = self.project_root / "compose.production.env"
        self.env_file.write_text("EXTERNAL_BACKUP_ENABLED=true\n", encoding="utf-8")
        self.state_directory = self.project_root / ".deploy"
        self.state_directory.mkdir()
        (self.state_directory / "current.json").write_text(
            json.dumps(
                {
                    "app_image": APP_IMAGE,
                    "backup_image": BACKUP_IMAGE,
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def build_controller(self, runner, times):
        time_values = iter(times)
        return operations.BackupOperationsController(
            project_root=self.project_root,
            env_file=self.env_file,
            state_directory=self.state_directory,
            runner=runner,
            monotonic=lambda: next(time_values),
        )

    def test_cycle_runs_local_external_and_reports_rpo(self):
        runner = FakeRunner()
        controller = self.build_controller(runner, (10.0, 25.0))

        report = controller.cycle(rpo_hours=26)

        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["rpo_actual_hours"], 2)
        self.assertEqual(report["elapsed_seconds"], 15)
        commands = [" ".join(call["command"]) for call in runner.calls]
        self.assertTrue(any(" up --detach --wait " in command for command in commands))
        self.assertTrue(any(" backup-monitor" in command for command in commands))
        self.assertTrue(
            any(
                " external-backup backup" in command
                for command in commands
            )
        )
        self.assertFalse(controller.lock_directory.exists())

    def test_drill_measures_rto_and_requires_matching_snapshot(self):
        runner = FakeRunner()
        controller = self.build_controller(runner, (100.0, 130.0))

        report = controller.drill(rpo_hours=26, rto_seconds=60)

        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["rto_actual_seconds"], 30)
        self.assertEqual(report["snapshot_id"], "a" * 64)

    def test_stale_backup_fails_rpo_and_releases_lock(self):
        runner = FakeRunner(age_hours=27)
        controller = self.build_controller(runner, (1.0, 2.0))

        with self.assertRaisesRegex(
            operations.BackupOperationError,
            "RPO incumplido",
        ):
            controller.cycle(rpo_hours=26)

        self.assertFalse(controller.lock_directory.exists())

    def test_slow_restore_fails_rto(self):
        runner = FakeRunner()
        controller = self.build_controller(runner, (5.0, 70.0))

        with self.assertRaisesRegex(
            operations.BackupOperationError,
            "RTO incumplido",
        ):
            controller.drill(rpo_hours=26, rto_seconds=60)

    def test_external_snapshot_must_match_local_backup(self):
        runner = FakeRunner(
            external_backup_id="20260620T070000Z",
        )
        controller = self.build_controller(runner, (1.0, 2.0))

        with self.assertRaisesRegex(
            operations.BackupOperationError,
            "no corresponde",
        ):
            controller.drill(rpo_hours=26, rto_seconds=60)

    def test_required_external_backup_cannot_be_skipped(self):
        runner = FakeRunner(
            external_statuses={
                "backup": "skipped",
                "verify-latest": "skipped",
            }
        )
        controller = self.build_controller(runner, (1.0, 2.0))

        with patch.dict(
            os.environ,
            {"BACKUP_REQUIRE_EXTERNAL": "true"},
            clear=False,
        ):
            with self.assertRaisesRegex(
                operations.BackupOperationError,
                "obligatoria",
            ):
                controller.cycle(rpo_hours=26)

    def test_existing_deployment_lock_blocks_operation(self):
        self.state_directory.with_name(".deploy.lock").mkdir()
        controller = self.build_controller(FakeRunner(), (1.0, 2.0))

        with self.assertRaisesRegex(
            operations.BackupOperationError,
            "otra operacion activa",
        ):
            controller.cycle(rpo_hours=26)

    def test_failure_alert_uses_configured_webhook(self):
        report = {
            "event": "recovery_drill",
            "status": "critical",
            "error": "RTO incumplido",
        }

        with patch.dict(
            os.environ,
            {
                "MONITOR_WEBHOOK_URL": "https://alerts.example/hook",
                "MONITOR_WEBHOOK_TOKEN": "test-token",
            },
            clear=False,
        ):
            with patch.object(operations, "send_webhook") as send_webhook:
                operations.alert_failure(report)

        self.assertEqual(report["alert"], "sent")
        send_webhook.assert_called_once()


if __name__ == "__main__":
    unittest.main()
