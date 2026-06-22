import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "fetch_release_manifest.py"
)
SPEC = importlib.util.spec_from_file_location(
    "fetch_release_manifest",
    SCRIPT_PATH,
)
fetcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fetcher)


APP_IMAGE = f"ghcr.io/example/vapes-shop@sha256:{'1' * 64}"
BACKUP_IMAGE = f"ghcr.io/example/vapes-shop-backup@sha256:{'2' * 64}"


class FakeRunner:
    def __init__(
        self,
        fail_attestation=False,
        extra_asset=False,
        corrupt_checksum=False,
    ):
        self.fail_attestation = fail_attestation
        self.extra_asset = extra_asset
        self.corrupt_checksum = corrupt_checksum
        self.commands = []

    def run(self, command):
        self.commands.append(command)

        if command[:3] == ["gh", "release", "download"]:
            output_directory = Path(
                command[command.index("--dir") + 1]
            )
            manifest_path = output_directory / "recovery-manifest.json"
            checksum_path = output_directory / "recovery-manifest.sha256"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema": "vapes-shop/recovery-manifest/v1",
                        "repository": "example/vapes-shop",
                        "release_tag": "v1.2.3",
                        "source_commit": "a" * 40,
                        "images": {
                            "application": APP_IMAGE,
                            "operations": BACKUP_IMAGE,
                        },
                        "recovery": {"rto_seconds": 1800.0},
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            digest = hashlib.sha256(
                manifest_path.read_bytes()
            ).hexdigest()
            checksum_path.write_text(
                (
                    f"{'0' * 64 if self.corrupt_checksum else digest}"
                    "  recovery-manifest.json\n"
                ),
                encoding="ascii",
            )

            if self.extra_asset:
                (output_directory / "unexpected.txt").write_text(
                    "unexpected\n",
                    encoding="utf-8",
                )

        if (
            command[:3] == ["gh", "attestation", "verify"]
            and self.fail_attestation
        ):
            raise fetcher.ReleaseFetchError(
                "atestacion invalida"
            )

        return ""


class ReleaseFetchTests(unittest.TestCase):
    def test_release_assets_are_downloaded_and_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory) / "release-assets"
            runner = FakeRunner()

            report = fetcher.fetch_release_manifest(
                repository="Example/Vapes-Shop",
                release_tag="v1.2.3",
                output_directory=output_directory,
                runner=runner,
            )

            self.assertEqual(report["status"], "verified")
            self.assertEqual(
                report["repository"],
                "example/vapes-shop",
            )
            self.assertEqual(report["app_image"], APP_IMAGE)
            self.assertTrue(
                (output_directory / "recovery-manifest.json").is_file()
            )
            self.assertEqual(
                runner.commands[1][:3],
                ["gh", "attestation", "verify"],
            )

    def test_failed_attestation_removes_untrusted_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory) / "release-assets"

            with self.assertRaises(fetcher.ReleaseFetchError):
                fetcher.fetch_release_manifest(
                    repository="example/vapes-shop",
                    release_tag="v1.2.3",
                    output_directory=output_directory,
                    runner=FakeRunner(fail_attestation=True),
                )

            self.assertFalse(output_directory.exists())

    def test_non_empty_destination_is_rejected_before_download(self):
        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory) / "release-assets"
            output_directory.mkdir()
            (output_directory / "existing.txt").write_text(
                "do not overwrite\n",
                encoding="utf-8",
            )
            runner = FakeRunner()

            with self.assertRaisesRegex(
                fetcher.ReleaseFetchError,
                "debe estar vacio",
            ):
                fetcher.fetch_release_manifest(
                    repository="example/vapes-shop",
                    release_tag="v1.2.3",
                    output_directory=output_directory,
                    runner=runner,
                )

            self.assertEqual(runner.commands, [])

    def test_unexpected_asset_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory) / "release-assets"

            with self.assertRaisesRegex(
                fetcher.ReleaseFetchError,
                "exactamente",
            ):
                fetcher.fetch_release_manifest(
                    repository="example/vapes-shop",
                    release_tag="v1.2.3",
                    output_directory=output_directory,
                    runner=FakeRunner(extra_asset=True),
                )

            self.assertFalse(output_directory.exists())

    def test_invalid_checksum_removes_downloaded_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory) / "release-assets"

            with self.assertRaisesRegex(
                fetcher.ReleaseManifestError,
                "checksum",
            ):
                fetcher.fetch_release_manifest(
                    repository="example/vapes-shop",
                    release_tag="v1.2.3",
                    output_directory=output_directory,
                    runner=FakeRunner(corrupt_checksum=True),
                )

            self.assertFalse(output_directory.exists())


if __name__ == "__main__":
    unittest.main()
