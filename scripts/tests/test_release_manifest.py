import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "release_manifest.py"
SPEC = importlib.util.spec_from_file_location("release_manifest", SCRIPT_PATH)
manifest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manifest)


REPOSITORY = "Example/Vapes-Shop"
TAG = "v1.2.3"
COMMIT = "a" * 40
APP_IMAGE = f"ghcr.io/example/vapes-shop@sha256:{'1' * 64}"
BACKUP_IMAGE = f"ghcr.io/example/vapes-shop-backup@sha256:{'2' * 64}"


class ReleaseManifestTests(unittest.TestCase):
    def valid_manifest(self):
        return manifest.build_manifest(
            repository=REPOSITORY,
            release_tag=TAG,
            source_commit=COMMIT,
            app_image=APP_IMAGE,
            backup_image=BACKUP_IMAGE,
            rto_seconds=1800,
        )

    def test_manifest_round_trip_validates_checksum_and_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "recovery-manifest.json"
            checksum_path = root / "recovery-manifest.sha256"
            payload = self.valid_manifest()
            manifest.write_manifest(manifest_path, payload)
            manifest.write_checksum(checksum_path, manifest_path)

            loaded = manifest.load_verified_manifest(
                manifest_path,
                checksum_path,
                expected_repository="example/vapes-shop",
                expected_tag=TAG,
            )

        self.assertEqual(loaded, payload)
        self.assertEqual(loaded["repository"], "example/vapes-shop")
        self.assertEqual(loaded["source_commit"], COMMIT)

    def test_changed_manifest_is_rejected_by_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "recovery-manifest.json"
            checksum_path = root / "recovery-manifest.sha256"
            manifest.write_manifest(manifest_path, self.valid_manifest())
            manifest.write_checksum(checksum_path, manifest_path)
            payload = json.loads(
                manifest_path.read_text(encoding="utf-8")
            )
            payload["source_commit"] = "b" * 40
            manifest_path.write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                manifest.ReleaseManifestError,
                "checksum",
            ):
                manifest.load_verified_manifest(
                    manifest_path,
                    checksum_path,
                    expected_repository=REPOSITORY,
                )

    def test_wrong_repository_is_rejected(self):
        payload = self.valid_manifest()

        with self.assertRaisesRegex(
            manifest.ReleaseManifestError,
            "repositorio esperado",
        ):
            manifest.validate_manifest(
                payload,
                expected_repository="attacker/repository",
            )

    def test_image_from_other_repository_is_rejected(self):
        payload = self.valid_manifest()
        payload["images"]["application"] = (
            f"ghcr.io/attacker/image@sha256:{'3' * 64}"
        )

        with self.assertRaisesRegex(
            manifest.ReleaseManifestError,
            "images.application",
        ):
            manifest.validate_manifest(payload)

    def test_mutable_image_is_rejected(self):
        with self.assertRaises(manifest.ReleaseManifestError):
            manifest.build_manifest(
                repository=REPOSITORY,
                release_tag=TAG,
                source_commit=COMMIT,
                app_image="ghcr.io/example/vapes-shop:latest",
                backup_image=BACKUP_IMAGE,
                rto_seconds=1800,
            )

    def test_non_semantic_tag_is_rejected(self):
        with self.assertRaisesRegex(
            manifest.ReleaseManifestError,
            "vMAJOR.MINOR.PATCH",
        ):
            manifest.build_manifest(
                repository=REPOSITORY,
                release_tag="production",
                source_commit=COMMIT,
                app_image=APP_IMAGE,
                backup_image=BACKUP_IMAGE,
                rto_seconds=1800,
            )

    def test_checksum_cannot_overwrite_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "recovery-manifest.json"
            manifest.write_manifest(manifest_path, self.valid_manifest())

            with self.assertRaisesRegex(
                manifest.ReleaseManifestError,
                "sobrescribir",
            ):
                manifest.write_checksum(manifest_path, manifest_path)

    def test_temporary_manifest_symlink_is_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "recovery-manifest.json"
            temporary_path = manifest_path.with_suffix(".json.tmp")

            def is_symlink(path):
                return path == temporary_path

            with patch.object(manifest.Path, "is_symlink", is_symlink):
                with self.assertRaisesRegex(
                    manifest.ReleaseManifestError,
                    "temporal simbolico",
                ):
                    manifest.write_manifest(
                        manifest_path,
                        self.valid_manifest(),
                    )

            self.assertFalse(manifest_path.exists())

    def test_temporary_checksum_symlink_is_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "recovery-manifest.json"
            checksum_path = root / "recovery-manifest.sha256"
            temporary_path = checksum_path.with_suffix(".sha256.tmp")
            manifest.write_manifest(manifest_path, self.valid_manifest())

            def is_symlink(path):
                return path == temporary_path

            with patch.object(manifest.Path, "is_symlink", is_symlink):
                with self.assertRaisesRegex(
                    manifest.ReleaseManifestError,
                    "temporal simbolico",
                ):
                    manifest.write_checksum(checksum_path, manifest_path)

            self.assertFalse(checksum_path.exists())


if __name__ == "__main__":
    unittest.main()
