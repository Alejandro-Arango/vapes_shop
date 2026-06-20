import importlib.util
import tempfile
import unittest
from pathlib import Path, PurePosixPath


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "check_secret_files.py"
SPEC = importlib.util.spec_from_file_location("check_secret_files", SCRIPT_PATH)
secret_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(secret_check)


class SecretFileCheckTests(unittest.TestCase):
    def test_real_environment_files_are_rejected(self):
        forbidden_paths = (
            PurePosixPath(".env"),
            PurePosixPath("compose.production.env"),
            PurePosixPath("config/private.pem"),
            PurePosixPath("id_ed25519"),
        )

        for forbidden_path in forbidden_paths:
            with self.subTest(path=forbidden_path):
                self.assertTrue(
                    secret_check.is_forbidden_path(forbidden_path)
                )

    def test_example_environment_files_are_allowed(self):
        allowed_paths = (
            PurePosixPath(".env.example"),
            PurePosixPath("compose.env.example"),
            PurePosixPath("compose.production.env.example"),
        )

        for allowed_path in allowed_paths:
            with self.subTest(path=allowed_path):
                self.assertFalse(
                    secret_check.is_forbidden_path(allowed_path)
                )

    def test_private_key_marker_is_detected(self):
        private_key = "-----BEGIN " + "PRIVATE KEY-----"

        self.assertIsNotNone(
            secret_check.find_content_marker(private_key)
        )

    def test_known_token_marker_is_detected(self):
        github_token = "ghp_" + ("A" * 36)

        self.assertIsNotNone(
            secret_check.find_content_marker(github_token)
        )

    def test_scan_reports_path_and_content_findings(self):
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)
            (project_root / ".env").write_text(
                "SECRET=value\n",
                encoding="utf-8",
            )
            (project_root / "notes.txt").write_text(
                "-----BEGIN " + "PRIVATE KEY-----",
                encoding="utf-8",
            )

            findings = secret_check.scan_tracked_files(
                project_root,
                (
                    PurePosixPath(".env"),
                    PurePosixPath("notes.txt"),
                ),
            )

        self.assertEqual(len(findings), 2)
        self.assertIn("archivo sensible", findings[0])
        self.assertIn("marcador de credencial", findings[1])


if __name__ == "__main__":
    unittest.main()
