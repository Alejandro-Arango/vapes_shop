import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "recover_production.py"
SPEC = importlib.util.spec_from_file_location("recover_production", SCRIPT_PATH)
recovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recovery)


APP_IMAGE = f"ghcr.io/example/vapes-shop@sha256:{'1' * 64}"
BACKUP_IMAGE = f"ghcr.io/example/vapes-shop-backup@sha256:{'2' * 64}"
BACKUP_ID = "20260621T120000Z"
SNAPSHOT_ID = "a" * 64


class FakeRunner:
    def __init__(
        self,
        existing_services="",
        existing_volumes="",
        catalog=None,
    ):
        self.existing_services = existing_services
        self.existing_volumes = existing_volumes
        self.catalog = (
            {"results": [{"id": 1}], "pagination": {}}
            if catalog is None
            else catalog
        )
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

        if " ps --all --services" in joined:
            return self.existing_services
        if "docker volume ls --quiet --filter" in joined:
            return self.existing_volumes
        if " external-recovery recover-latest " in joined:
            return json.dumps(
                {
                    "status": "recovered",
                    "backup_id": BACKUP_ID,
                    "snapshot_id": SNAPSHOT_ID,
                }
            )
        if "/api/products/" in joined:
            return json.dumps(self.catalog)
        return ""


class ProductionRecoveryTests(unittest.TestCase):
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
        self.env_file = self.root / "compose.production.env"
        self.env_file.write_text(
            (
                "DJANGO_ALLOWED_HOSTS=shop.example,www.shop.example\n"
                "DJANGO_SECRET_KEY=test\n"
            ),
            encoding="utf-8",
        )
        self.state_directory = self.root / ".deploy"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def controller(self, runner, times=(100.0, 130.0)):
        values = iter(times)
        return recovery.ProductionRecoveryController(
            project_root=self.root,
            env_file=self.env_file,
            state_directory=self.state_directory,
            runner=runner,
            command_timeout=900,
            wait_timeout=60,
            monotonic=lambda: next(values),
        )

    def test_recovery_restores_data_starts_service_and_writes_state(self):
        runner = FakeRunner()
        controller = self.controller(runner)

        report = controller.recover(
            APP_IMAGE,
            BACKUP_IMAGE,
            rto_seconds=1800,
        )

        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["backup_id"], BACKUP_ID)
        self.assertEqual(report["rto_actual_seconds"], 30.0)
        self.assertEqual(report["catalog_probe_products"], 1)
        state = json.loads(
            (self.state_directory / "current.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(state["recovered_from_backup"], BACKUP_ID)
        commands = [
            " ".join(call["command"])
            for call in runner.calls
        ]
        external_index = next(
            index
            for index, command in enumerate(commands)
            if " external-recovery recover-latest " in command
        )
        restore_index = next(
            index
            for index, command in enumerate(commands)
            if command.endswith(" run --rm --no-deps restore")
        )
        migrate_index = next(
            index
            for index, command in enumerate(commands)
            if command.endswith(" run --rm --no-deps migrate")
        )
        self.assertLess(external_index, restore_index)
        self.assertLess(restore_index, migrate_index)
        restore_call = next(
            call
            for call in runner.calls
            if " ".join(call["command"]).endswith(
                " run --rm --no-deps restore"
            )
        )
        self.assertEqual(
            restore_call["environment"]["RESTORE_CONFIRM"],
            f"RESTORE-{BACKUP_ID}",
        )
        self.assertEqual(
            restore_call["environment"]["RESTORE_CREATE_SAFETY_BACKUP"],
            "false",
        )
        self.assertEqual(
            restore_call["environment"]["COMPOSE_PROJECT_NAME"],
            "vapes-shop",
        )

    def test_existing_productive_state_blocks_recovery(self):
        self.state_directory.mkdir()
        (self.state_directory / "current.json").write_text(
            "{}\n",
            encoding="utf-8",
        )
        runner = FakeRunner()

        with self.assertRaisesRegex(
            recovery.ProductionRecoveryError,
            "Ya existe estado productivo",
        ):
            self.controller(runner).recover(
                APP_IMAGE,
                BACKUP_IMAGE,
                rto_seconds=1800,
            )

        self.assertEqual(runner.calls, [])

    def test_existing_containers_block_recovery_and_release_lock(self):
        runner = FakeRunner(existing_services="db\n")

        with self.assertRaisesRegex(
            recovery.ProductionRecoveryError,
            "no existan contenedores previos",
        ):
            self.controller(runner).recover(
                APP_IMAGE,
                BACKUP_IMAGE,
                rto_seconds=1800,
            )

        self.assertFalse(
            self.state_directory.with_name(".deploy.lock").exists()
        )

    def test_existing_volumes_block_recovery(self):
        runner = FakeRunner(existing_volumes="vapes-shop_mysql_data\n")

        with self.assertRaisesRegex(
            recovery.ProductionRecoveryError,
            "no existan volumenes previos",
        ):
            self.controller(runner).recover(
                APP_IMAGE,
                BACKUP_IMAGE,
                rto_seconds=1800,
            )

        commands = [
            " ".join(call["command"])
            for call in runner.calls
        ]
        self.assertFalse(
            any(" external-recovery " in command for command in commands)
        )

    def test_recovered_service_reports_rto_violation(self):
        runner = FakeRunner()
        controller = self.controller(runner, times=(100.0, 2001.0))

        report = controller.recover(
            APP_IMAGE,
            BACKUP_IMAGE,
            rto_seconds=1800,
        )

        self.assertEqual(report["status"], "critical")
        self.assertIn("RTO integral incumplido", report["error"])
        self.assertTrue(
            (self.state_directory / "current.json").is_file()
        )

    def test_invalid_catalog_response_blocks_success_state(self):
        runner = FakeRunner(catalog={"error": "unexpected"})

        with self.assertRaisesRegex(
            recovery.ProductionRecoveryError,
            "no devolvio results",
        ):
            self.controller(runner).recover(
                APP_IMAGE,
                BACKUP_IMAGE,
                rto_seconds=1800,
            )

        self.assertFalse(
            (self.state_directory / "current.json").exists()
        )

    def test_mutable_image_is_rejected_before_commands(self):
        runner = FakeRunner()

        with self.assertRaises(recovery.ProductionRecoveryError):
            self.controller(runner).recover(
                "ghcr.io/example/vapes-shop:latest",
                BACKUP_IMAGE,
                rto_seconds=1800,
            )

        self.assertEqual(runner.calls, [])

    def test_rto_objective_is_loaded_from_production_environment(self):
        self.env_file.write_text(
            (
                "DJANGO_ALLOWED_HOSTS=shop.example\n"
                "DISASTER_RECOVERY_RTO_SECONDS=2400\n"
            ),
            encoding="utf-8",
        )

        objective = recovery.load_rto_objective(self.env_file)

        self.assertEqual(objective, 2400.0)


if __name__ == "__main__":
    unittest.main()
