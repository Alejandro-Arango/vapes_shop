import importlib.util
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "verify_recovery.py"
SPEC = importlib.util.spec_from_file_location("verify_recovery", SCRIPT_PATH)
recovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recovery)


class RecoveryHandler(BaseHTTPRequestHandler):
    unhealthy_requests = 0
    requests = 0

    def do_GET(self):
        type(self).requests += 1
        healthy = type(self).requests > type(self).unhealthy_requests
        status_code = 200 if healthy else 503
        payload = {
            "status": "ok" if healthy else "error",
            "database": "available" if healthy else "unavailable",
            "cache": "available" if healthy else "not_checked",
        }
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Request-ID", f"recovery-{type(self).requests}")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format_string, *args):
        return


class RecoveryVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            RecoveryHandler,
        )
        cls.thread = threading.Thread(
            target=cls.server.serve_forever,
            daemon=True,
        )
        cls.thread.start()
        host, port = cls.server.server_address
        cls.url = f"http://{host}:{port}/healthz"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        RecoveryHandler.requests = 0
        RecoveryHandler.unhealthy_requests = 0

    def test_recovery_requires_consecutive_healthy_responses(self):
        RecoveryHandler.unhealthy_requests = 2

        exit_code, report = recovery.verify_recovery(
            self.url,
            budget=5,
            interval=0,
            timeout=1,
            consecutive=3,
            allow_http=True,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], "recovered")
        self.assertEqual(report["attempts"], 5)
        self.assertEqual(report["consecutive_successes"], 3)
        self.assertEqual(len(report["errors"]), 2)

    def test_recovery_timeout_is_reported(self):
        RecoveryHandler.unhealthy_requests = 100
        times = iter((0.0, 0.0, 0.5, 1.1, 1.1))

        exit_code, report = recovery.verify_recovery(
            self.url,
            budget=1,
            interval=0,
            timeout=1,
            consecutive=2,
            allow_http=True,
            sleep=lambda _: None,
            monotonic=lambda: next(times),
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(report["status"], "timeout")
        self.assertGreaterEqual(report["attempts"], 1)

    def test_invalid_configuration_is_rejected(self):
        with self.assertRaises(recovery.MonitorError):
            recovery.verify_recovery(
                self.url,
                budget=0,
                allow_http=True,
            )

    def test_report_file_is_written_with_restricted_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "recovery-report.json"

            with patch.object(recovery.os, "chmod") as chmod:
                recovery.write_report(report_path, {"status": "recovered"})

            chmod.assert_called_once_with(
                report_path.with_suffix(".json.tmp"),
                0o600,
            )
            self.assertEqual(
                json.loads(report_path.read_text(encoding="utf-8")),
                {"status": "recovered"},
            )

    def test_report_symlink_paths_are_rejected_before_write(self):
        for blocked_name in ("output", "parent", "temporary"):
            with self.subTest(blocked_name=blocked_name):
                with tempfile.TemporaryDirectory() as directory:
                    report_path = Path(directory) / "recovery-report.json"
                    temporary_path = report_path.with_suffix(".json.tmp")
                    blocked_path = {
                        "output": report_path,
                        "parent": report_path.parent,
                        "temporary": temporary_path,
                    }[blocked_name]

                    def is_symlink(path):
                        return path == blocked_path

                    with patch.object(recovery.Path, "is_symlink", is_symlink):
                        with self.assertRaisesRegex(
                            recovery.MonitorError,
                            "reporte de recuperacion no admite enlaces simbolicos",
                        ):
                            recovery.write_report(
                                report_path,
                                {"status": "recovered"},
                            )

                    self.assertFalse(report_path.exists())


if __name__ == "__main__":
    unittest.main()
