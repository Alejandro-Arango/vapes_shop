import gzip
import hashlib
import importlib.util
import io
import json
import tarfile
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "monitor_backups.py"
SPEC = importlib.util.spec_from_file_location("monitor_backups", SCRIPT_PATH)
monitor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(monitor)


class DiskUsage:
    total = 10_000_000
    used = 1_000_000
    free = 9_000_000


class BackupMonitorTests(unittest.TestCase):
    def create_backup(self, root, created_at=None):
        created_at = created_at or datetime.now(timezone.utc)
        backup_id = created_at.strftime("%Y%m%dT%H%M%SZ")
        backup_directory = root / backup_id
        backup_directory.mkdir()
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
        manifest_lines = []

        for name in monitor.PAYLOAD_FILES:
            digest = hashlib.sha256(
                (backup_directory / name).read_bytes()
            ).hexdigest()
            manifest_lines.append(f"{digest}  {name}")

        (backup_directory / "manifest.sha256").write_text(
            "\n".join(manifest_lines) + "\n",
            encoding="ascii",
        )
        (root / "latest.txt").write_text(backup_id + "\n", encoding="ascii")
        return backup_directory

    def verify(self, root, now=None, **overrides):
        current_time = now or datetime.now(timezone.utc)
        options = {
            "backup_root": root,
            "max_age_hours": 26,
            "min_database_bytes": 128,
            "min_media_bytes": 32,
            "min_free_bytes": 1,
            "min_free_percent": 1,
            "min_free_copies": 1,
            "now": lambda: current_time,
            "disk_usage": lambda _: DiskUsage(),
        }
        options.update(overrides)
        return monitor.verify_backup(**options)

    def test_valid_backup_reports_age_integrity_and_capacity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            created_at = datetime.now(timezone.utc).replace(microsecond=0)
            self.create_backup(root, created_at)

            report = self.verify(root, now=created_at + timedelta(hours=2))

        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["age_hours"], 2)
        self.assertGreater(report["database_uncompressed_bytes"], 128)
        self.assertEqual(report["media_members"], 1)

    def test_stale_backup_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            created_at = datetime.now(timezone.utc).replace(microsecond=0)
            self.create_backup(root, created_at)

            with self.assertRaisesRegex(
                monitor.BackupMonitorError,
                "antiguedad",
            ):
                self.verify(
                    root,
                    now=created_at + timedelta(hours=27),
                )

    def test_checksum_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backup_directory = self.create_backup(root)
            (backup_directory / "metadata.txt").write_text(
                "contenido alterado\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                monitor.BackupMonitorError,
                "Checksum invalido",
            ):
                self.verify(root)

    def test_unsafe_media_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backup_directory = self.create_backup(root)
            media_path = backup_directory / "media.tar.gz"

            with tarfile.open(media_path, "w:gz") as archive:
                content = b"unsafe"
                info = tarfile.TarInfo("../escape.txt")
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))

            manifest_path = backup_directory / "manifest.sha256"
            lines = manifest_path.read_text(encoding="ascii").splitlines()
            digest = hashlib.sha256(media_path.read_bytes()).hexdigest()
            manifest_path.write_text(
                "\n".join(
                    (
                        lines[0],
                        f"{digest}  media.tar.gz",
                        lines[2],
                        "",
                    )
                ),
                encoding="ascii",
            )

            with self.assertRaisesRegex(
                monitor.BackupMonitorError,
                "ruta insegura",
            ):
                self.verify(root)

    def test_low_disk_space_is_rejected(self):
        class LowDisk:
            total = 1000
            used = 950
            free = 50

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.create_backup(root)

            with self.assertRaisesRegex(
                monitor.BackupMonitorError,
                "espacio",
            ):
                self.verify(
                    root,
                    min_free_bytes=100,
                    disk_usage=lambda _: LowDisk(),
                )

    def test_backup_root_symlink_is_rejected_before_reading_latest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backup_root = root / "backups"
            backup_root.mkdir()

            def is_symlink(path):
                return path == backup_root

            with patch.object(monitor.Path, "is_symlink", is_symlink):
                with self.assertRaisesRegex(
                    monitor.BackupMonitorError,
                    "BACKUP_ROOT no puede ser un enlace simbolico",
                ):
                    self.verify(backup_root)

    def test_backup_root_parent_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backup_root = root / "backups"
            backup_root.mkdir()

            def is_symlink(path):
                return path == root

            with patch.object(monitor.Path, "is_symlink", is_symlink):
                with self.assertRaisesRegex(
                    monitor.BackupMonitorError,
                    "BACKUP_ROOT no puede ser un enlace simbolico",
                ):
                    self.verify(backup_root)

    def test_run_monitor_reports_critical_without_webhook(self):
        with tempfile.TemporaryDirectory() as directory:
            exit_code, event = monitor.run_monitor(
                backup_root=directory,
                min_free_bytes=0,
                min_free_percent=0,
                min_free_copies=0,
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(event["status"], "critical")
        self.assertEqual(event["alert"], "not_configured")

    def test_run_monitor_sends_webhook_after_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(monitor, "send_webhook") as send_webhook:
                exit_code, event = monitor.run_monitor(
                    backup_root=directory,
                    min_free_bytes=0,
                    min_free_percent=0,
                    min_free_copies=0,
                    webhook_url="https://alerts.example/hook",
                    webhook_token="test-token",
                )

        self.assertEqual(exit_code, 1)
        self.assertEqual(event["alert"], "sent")
        send_webhook.assert_called_once()

    def test_report_file_is_written_with_restricted_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "backup-monitor-report.json"

            with patch.object(monitor.os, "chmod") as chmod:
                monitor.write_report(report_path, {"status": "ok"})

            chmod.assert_called_once_with(
                report_path.with_suffix(".json.tmp"),
                0o600,
            )
            self.assertEqual(
                json.loads(report_path.read_text(encoding="utf-8")),
                {"status": "ok"},
            )

    def test_report_symlink_paths_are_rejected_before_write(self):
        for blocked_name in ("output", "parent", "temporary"):
            with self.subTest(blocked_name=blocked_name):
                with tempfile.TemporaryDirectory() as directory:
                    report_path = Path(directory) / "backup-monitor-report.json"
                    temporary_path = report_path.with_suffix(".json.tmp")
                    blocked_path = {
                        "output": report_path,
                        "parent": report_path.parent,
                        "temporary": temporary_path,
                    }[blocked_name]

                    def is_symlink(path):
                        return path == blocked_path

                    with patch.object(monitor.Path, "is_symlink", is_symlink):
                        with self.assertRaisesRegex(
                            monitor.BackupMonitorError,
                            (
                                "reporte de monitoreo de backups "
                                "no admite enlaces simbolicos"
                            ),
                        ):
                            monitor.write_report(
                                report_path,
                                {"status": "ok"},
                            )

                    self.assertFalse(report_path.exists())

    def test_existing_temporary_report_is_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "backup-monitor-report.json"
            temporary_path = report_path.with_suffix(".json.tmp")
            temporary_path.write_text("stale\n", encoding="utf-8")

            with self.assertRaisesRegex(
                monitor.BackupMonitorError,
                "temporales preexistentes",
            ):
                monitor.write_report(report_path, {"status": "ok"})

            self.assertFalse(report_path.exists())
            self.assertEqual(
                temporary_path.read_text(encoding="utf-8"),
                "stale\n",
            )


if __name__ == "__main__":
    unittest.main()
