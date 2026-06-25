import gzip
import hashlib
import importlib.util
import io
import json
import os
import shutil
import tarfile
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "external_backup.py"
SPEC = importlib.util.spec_from_file_location("external_backup", SCRIPT_PATH)
external = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(external)


class FakeRunner:
    def __init__(self, backup_root, corrupt_restore=False):
        self.backup_root = Path(backup_root).resolve()
        self.corrupt_restore = corrupt_restore
        self.commands = []
        self.working_directories = []

    def run(self, command, cwd=None):
        self.commands.append(command)
        self.working_directories.append(cwd)

        if command[1] == "backup":
            return json.dumps(
                {
                    "message_type": "summary",
                    "snapshot_id": "a" * 64,
                    "files_new": 4,
                    "data_added": 1024,
                }
            )

        if command[1] == "snapshots":
            return json.dumps([{"id": "b" * 64}])

        if command[1] == "restore":
            target = Path(command[command.index("--target") + 1])
            shutil.copytree(
                self.backup_root,
                target,
                dirs_exist_ok=True,
            )

            if self.corrupt_restore:
                backup_id = (
                    target / "latest.txt"
                ).read_text(encoding="ascii").strip()
                (
                    target / backup_id / "metadata.txt"
                ).write_text("alterado\n", encoding="utf-8")

        return ""


class ExternalBackupTests(unittest.TestCase):
    def create_backup(self, root):
        created_at = datetime.now(timezone.utc).replace(microsecond=0)
        backup_id = created_at.strftime("%Y%m%dT%H%M%SZ")
        backup_directory = root / backup_id
        backup_directory.mkdir(parents=True)
        database_path = backup_directory / "database.sql.gz"
        media_path = backup_directory / "media.tar.gz"
        metadata_path = backup_directory / "metadata.txt"

        with gzip.open(database_path, "wb") as database:
            database.write(b"CREATE TABLE probe (id INT);\n" * 20)

        with tarfile.open(media_path, "w:gz") as archive:
            content = b"persistent-media\n"
            info = tarfile.TarInfo("store/img/products/probe.txt")
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))

        metadata_path.write_text(
            "\n".join(
                (
                    f"backup_id={backup_id}",
                    (
                        "created_at_utc="
                        f"{created_at.strftime('%Y-%m-%dT%H:%M:%SZ')}"
                    ),
                    "database=vapes_shop",
                    "mysql_host=db",
                    "",
                )
            ),
            encoding="utf-8",
        )
        manifest = []

        for name in ("database.sql.gz", "media.tar.gz", "metadata.txt"):
            digest = hashlib.sha256(
                (backup_directory / name).read_bytes()
            ).hexdigest()
            manifest.append(f"{digest}  {name}")

        (backup_directory / "manifest.sha256").write_text(
            "\n".join(manifest) + "\n",
            encoding="ascii",
        )
        (root / "latest.txt").write_text(backup_id + "\n", encoding="ascii")
        return backup_id

    def base_environment(self, root, restore_root):
        return {
            "BACKUP_ROOT": str(root),
            "BACKUP_MAX_AGE_HOURS": "26",
            "BACKUP_MIN_DATABASE_BYTES": "128",
            "BACKUP_MIN_MEDIA_BYTES": "32",
            "EXTERNAL_BACKUP_HOST": "test-host",
            "EXTERNAL_BACKUP_CHECK_SUBSET": "5%",
            "EXTERNAL_BACKUP_KEEP_DAILY": "14",
            "EXTERNAL_BACKUP_KEEP_WEEKLY": "8",
            "EXTERNAL_BACKUP_KEEP_MONTHLY": "12",
            "EXTERNAL_BACKUP_RESTORE_ROOT": str(restore_root),
        }

    def test_backup_is_checked_restored_and_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            root = workspace / "backups"
            restore_root = workspace / "restore"
            root.mkdir()
            backup_id = self.create_backup(root)
            runner = FakeRunner(root)

            with patch.dict(
                os.environ,
                self.base_environment(root, restore_root),
                clear=False,
            ):
                report = external.create_external_backup(runner)

        self.assertEqual(report["status"], "stored_and_restored")
        self.assertEqual(report["backup_id"], backup_id)
        self.assertEqual(report["snapshot_id"], "a" * 64)
        actions = [command[1] for command in runner.commands]
        self.assertEqual(actions, ["backup", "check", "restore", "forget"])
        self.assertEqual(runner.working_directories[0], root.resolve())

    def test_restore_corruption_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            root = workspace / "backups"
            restore_root = workspace / "restore"
            root.mkdir()
            self.create_backup(root)
            runner = FakeRunner(root, corrupt_restore=True)

            with patch.dict(
                os.environ,
                self.base_environment(root, restore_root),
                clear=False,
            ):
                with self.assertRaisesRegex(
                    external.ExternalBackupError,
                    "altero metadata.txt",
                ):
                    external.create_external_backup(runner)

    def test_latest_snapshot_can_be_verified_without_new_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            root = workspace / "backups"
            restore_root = workspace / "restore"
            root.mkdir()
            backup_id = self.create_backup(root)
            runner = FakeRunner(root)

            with patch.dict(
                os.environ,
                self.base_environment(root, restore_root),
                clear=False,
            ):
                report = external.verify_latest_external_backup(runner)

        self.assertEqual(report["status"], "verified")
        self.assertEqual(report["snapshot_id"], "b" * 64)
        self.assertEqual(report["backup_id"], backup_id)
        actions = [command[1] for command in runner.commands]
        self.assertEqual(actions, ["snapshots", "check", "restore"])

    def test_latest_snapshot_can_be_materialized_on_empty_host(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            source_root = workspace / "source"
            recovered_root = workspace / "recovered"
            restore_root = workspace / "restore"
            source_root.mkdir()
            recovered_root.mkdir()
            backup_id = self.create_backup(source_root)
            runner = FakeRunner(source_root)

            with patch.dict(
                os.environ,
                self.base_environment(recovered_root, restore_root),
                clear=False,
            ):
                report = external.recover_latest_external_backup(
                    runner,
                    external.RECOVERY_CONFIRMATION,
                )

            self.assertEqual(report["status"], "recovered")
            self.assertEqual(report["backup_id"], backup_id)
            self.assertEqual(
                (recovered_root / "latest.txt")
                .read_text(encoding="ascii")
                .strip(),
                backup_id,
            )
            self.assertTrue(
                (recovered_root / backup_id / "database.sql.gz").is_file()
            )

        actions = [command[1] for command in runner.commands]
        self.assertEqual(actions, ["snapshots", "check", "restore"])

    def test_external_recovery_requires_empty_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            source_root = workspace / "source"
            recovered_root = workspace / "recovered"
            restore_root = workspace / "restore"
            source_root.mkdir()
            recovered_root.mkdir()
            self.create_backup(source_root)
            (recovered_root / "existing.txt").write_text(
                "do not overwrite\n",
                encoding="utf-8",
            )
            runner = FakeRunner(source_root)

            with patch.dict(
                os.environ,
                self.base_environment(recovered_root, restore_root),
                clear=False,
            ):
                with self.assertRaisesRegex(
                    external.ExternalBackupError,
                    "debe estar vacio",
                ):
                    external.recover_latest_external_backup(
                        runner,
                        external.RECOVERY_CONFIRMATION,
                    )

        self.assertEqual(runner.commands, [])

    def test_external_recovery_requires_exact_confirmation(self):
        runner = FakeRunner(".")

        with self.assertRaisesRegex(
            external.ExternalBackupError,
            external.RECOVERY_CONFIRMATION,
        ):
            external.recover_latest_external_backup(
                runner,
                "incorrect",
            )

    def test_initialization_requires_exact_confirmation(self):
        runner = FakeRunner(".")

        with self.assertRaisesRegex(
            external.ExternalBackupError,
            external.INIT_CONFIRMATION,
        ):
            external.initialize_repository(runner, "incorrect")

        report = external.initialize_repository(
            runner,
            external.INIT_CONFIRMATION,
        )

        self.assertEqual(report["status"], "initialized")
        self.assertEqual(runner.commands[-1], ["restic", "init"])

    def test_secret_files_require_strong_password_and_safe_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository_file = root / "repository.txt"
            password_file = root / "password.txt"
            repository_file.write_text(
                "rest:https://user:password@example.com/repo\n",
                encoding="utf-8",
            )
            password_file.write_text("short\n", encoding="utf-8")

            with patch.dict(
                os.environ,
                {
                    "RESTIC_REPOSITORY_FILE": str(repository_file),
                    "RESTIC_PASSWORD_FILE": str(password_file),
                },
                clear=False,
            ):
                with self.assertRaises(external.ExternalBackupError):
                    external.validate_secret_files()

            repository_file.write_text(
                "s3:https://storage.example/bucket/repo\n",
                encoding="utf-8",
            )
            password_file.write_text(
                "long-random-password-for-restic-123456\n",
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {
                    "RESTIC_REPOSITORY_FILE": str(repository_file),
                    "RESTIC_PASSWORD_FILE": str(password_file),
                },
                clear=False,
            ):
                result = external.validate_secret_files()

        self.assertEqual(
            result["repository_file"],
            str(repository_file),
        )

    def test_invalid_check_subset_is_rejected(self):
        runner = FakeRunner(".")

        with patch.dict(
            os.environ,
            {"EXTERNAL_BACKUP_CHECK_SUBSET": "all"},
            clear=False,
        ):
            with self.assertRaisesRegex(
                external.ExternalBackupError,
                "porcentaje o fraccion",
            ):
                external.check_repository(runner)

    def test_report_file_is_written_with_restricted_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "external-backup-report.json"

            with patch.object(external.os, "chmod") as chmod:
                external.write_report(report_path, {"status": "ok"})

            chmod.assert_called_once_with(
                report_path.with_suffix(".json.tmp"),
                0o600,
            )

    def test_report_output_symlink_is_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "external-backup-report.json"

            def is_symlink(path):
                return path == report_path

            with patch.object(external.Path, "is_symlink", is_symlink):
                with self.assertRaisesRegex(
                    external.ExternalBackupError,
                    "reporte de backup externo no admite enlaces simbolicos",
                ):
                    external.write_report(report_path, {"status": "ok"})

            self.assertFalse(report_path.exists())

    def test_report_parent_symlink_is_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "external-backup-report.json"

            def is_symlink(path):
                return path == report_path.parent

            with patch.object(external.Path, "is_symlink", is_symlink):
                with self.assertRaisesRegex(
                    external.ExternalBackupError,
                    "reporte de backup externo no admite enlaces simbolicos",
                ):
                    external.write_report(report_path, {"status": "ok"})

            self.assertFalse(report_path.exists())

    def test_temporary_report_symlink_is_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "external-backup-report.json"
            temporary_path = report_path.with_suffix(".json.tmp")

            def is_symlink(path):
                return path == temporary_path

            with patch.object(external.Path, "is_symlink", is_symlink):
                with self.assertRaisesRegex(
                    external.ExternalBackupError,
                    "reporte de backup externo no admite enlaces simbolicos",
                ):
                    external.write_report(report_path, {"status": "ok"})

            self.assertFalse(report_path.exists())


if __name__ == "__main__":
    unittest.main()
