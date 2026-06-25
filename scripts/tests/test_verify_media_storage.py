import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "verify_media_storage.py"
SPEC = importlib.util.spec_from_file_location(
    "verify_media_storage",
    SCRIPT_PATH,
)
media = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(media)


class ProbeContent:
    def __init__(self, content, name=""):
        self.content = content
        self.name = name


class MemoryStorage:
    def __init__(self, writable=True):
        self.files = {
            "operational/persistent.txt": b"persistent-media\n",
        }
        self.writable = writable

    class Reader:
        def __init__(self, content):
            self.content = content

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return self.content

    def open(self, name, mode):
        if mode != "rb" or name not in self.files:
            raise OSError("Archivo no disponible.")

        return self.Reader(self.files[name])

    def save(self, name, content):
        if not self.writable:
            raise PermissionError("Volumen sin permisos de escritura.")

        self.files[name] = content.content
        return name

    def exists(self, name):
        return name in self.files

    def delete(self, name):
        self.files.pop(name, None)


class MediaStorageVerifierTests(unittest.TestCase):
    def test_available_storage_preserves_marker_and_cleans_probe(self):
        storage = MemoryStorage(writable=True)

        report = media.probe_storage(
            storage,
            ProbeContent,
            "available",
            "operational/persistent.txt",
            "persistent-media\n",
            token="available",
        )

        self.assertEqual(report["status"], "available")
        self.assertEqual(report["write_error"], "")
        self.assertEqual(
            storage.files,
            {"operational/persistent.txt": b"persistent-media\n"},
        )

    def test_unavailable_storage_keeps_existing_marker_readable(self):
        storage = MemoryStorage(writable=False)

        report = media.probe_storage(
            storage,
            ProbeContent,
            "unavailable",
            "operational/persistent.txt",
            "persistent-media\n",
            token="unavailable",
        )

        self.assertEqual(report["status"], "unavailable_as_expected")
        self.assertEqual(report["write_error"], "PermissionError")
        self.assertEqual(
            storage.files["operational/persistent.txt"],
            b"persistent-media\n",
        )

    def test_unexpected_write_success_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "debia rechazar"):
            media.probe_storage(
                MemoryStorage(writable=True),
                ProbeContent,
                "unavailable",
                "operational/persistent.txt",
                "persistent-media\n",
                token="unexpected",
            )

    def test_changed_marker_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "no conserva"):
            media.probe_storage(
                MemoryStorage(writable=True),
                ProbeContent,
                "available",
                "operational/persistent.txt",
                "other-value\n",
            )

    def test_unsafe_marker_name_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "ruta relativa segura"):
            media.probe_storage(
                MemoryStorage(writable=True),
                ProbeContent,
                "available",
                "../persistent.txt",
                "persistent-media\n",
            )

    def test_report_file_is_written_with_restricted_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "media-report.json"

            with patch.object(media.os, "chmod") as chmod:
                media.write_report(report_path, {"status": "available"})

            chmod.assert_called_once_with(
                report_path.with_suffix(".json.tmp"),
                0o600,
            )
            self.assertEqual(
                json.loads(report_path.read_text(encoding="utf-8")),
                {"status": "available"},
            )

    def test_report_symlink_paths_are_rejected_before_write(self):
        for blocked_name in ("output", "parent", "temporary"):
            with self.subTest(blocked_name=blocked_name):
                with tempfile.TemporaryDirectory() as directory:
                    report_path = Path(directory) / "media-report.json"
                    temporary_path = report_path.with_suffix(".json.tmp")
                    blocked_path = {
                        "output": report_path,
                        "parent": report_path.parent,
                        "temporary": temporary_path,
                    }[blocked_name]

                    def is_symlink(path):
                        return path == blocked_path

                    with patch.object(media.Path, "is_symlink", is_symlink):
                        with self.assertRaisesRegex(
                            RuntimeError,
                            (
                                "reporte de almacenamiento media "
                                "no admite enlaces simbolicos"
                            ),
                        ):
                            media.write_report(
                                report_path,
                                {"status": "available"},
                            )

                    self.assertFalse(report_path.exists())


if __name__ == "__main__":
    unittest.main()
