import importlib.util
import hashlib
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
        checkout_commit="a" * 40,
        tracked_changes="",
        catalog=None,
    ):
        self.existing_services = existing_services
        self.existing_volumes = existing_volumes
        self.checkout_commit = checkout_commit
        self.tracked_changes = tracked_changes
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

        if " rev-parse --is-inside-work-tree" in joined:
            return "true\n"
        if " rev-parse HEAD" in joined:
            return f"{self.checkout_commit}\n"
        if " status --porcelain=v1 --untracked-files=no" in joined:
            return self.tracked_changes
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
            release_tag="v1.2.3",
            source_commit="a" * 40,
        )

        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["backup_id"], BACKUP_ID)
        self.assertEqual(report["rto_actual_seconds"], 30.0)
        self.assertEqual(report["catalog_probe_products"], 1)
        self.assertEqual(report["release_tag"], "v1.2.3")
        self.assertEqual(report["source_commit"], "a" * 40)
        self.assertTrue(report["source_checkout_verified"])
        state = json.loads(
            (self.state_directory / "current.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(state["recovered_from_backup"], BACKUP_ID)
        self.assertEqual(state["release_tag"], "v1.2.3")
        self.assertEqual(state["source_commit"], "a" * 40)
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

    def test_manifest_commit_must_match_local_checkout(self):
        runner = FakeRunner(checkout_commit="b" * 40)

        with self.assertRaisesRegex(
            recovery.ProductionRecoveryError,
            "no coincide con source_commit",
        ):
            self.controller(runner).recover(
                APP_IMAGE,
                BACKUP_IMAGE,
                rto_seconds=1800,
                release_tag="v1.2.3",
                source_commit="a" * 40,
            )

        commands = [
            " ".join(call["command"])
            for call in runner.calls
        ]
        self.assertFalse(any("docker compose" in item for item in commands))

    def test_tracked_changes_block_manifest_recovery(self):
        runner = FakeRunner(tracked_changes=" M compose.yaml\n")

        with self.assertRaisesRegex(
            recovery.ProductionRecoveryError,
            "cambios rastreados",
        ):
            self.controller(runner).recover(
                APP_IMAGE,
                BACKUP_IMAGE,
                rto_seconds=1800,
                release_tag="v1.2.3",
                source_commit="a" * 40,
            )

        self.assertFalse(
            self.state_directory.with_name(".deploy.lock").exists()
        )

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

    def test_verified_release_manifest_supplies_images_and_identity(self):
        manifest_path = self.root / "recovery-manifest.json"
        checksum_path = self.root / "recovery-manifest.sha256"
        payload = {
            "schema": "vapes-shop/recovery-manifest/v1",
            "repository": "example/vapes-shop",
            "release_tag": "v1.2.3",
            "source_commit": "a" * 40,
            "images": {
                "application": APP_IMAGE,
                "operations": BACKUP_IMAGE,
            },
            "recovery": {"rto_seconds": 1800.0},
        }
        manifest_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        checksum_path.write_text(
            f"{digest}  recovery-manifest.json\n",
            encoding="ascii",
        )

        source = recovery.load_recovery_source(
            app_image="",
            backup_image="",
            release_manifest=str(manifest_path),
            manifest_checksum=str(checksum_path),
            expected_repository="example/vapes-shop",
            expected_tag="v1.2.3",
        )

        self.assertEqual(source["app_image"], APP_IMAGE)
        self.assertEqual(source["backup_image"], BACKUP_IMAGE)
        self.assertEqual(source["release_tag"], "v1.2.3")
        self.assertEqual(source["source_commit"], "a" * 40)

    def test_manifest_cannot_be_combined_with_explicit_images(self):
        with self.assertRaisesRegex(
            recovery.ProductionRecoveryError,
            "No combines",
        ):
            recovery.load_recovery_source(
                app_image=APP_IMAGE,
                backup_image=BACKUP_IMAGE,
                release_manifest="manifest.json",
                manifest_checksum="manifest.sha256",
                expected_repository="example/vapes-shop",
            )


if __name__ == "__main__":
    unittest.main()
