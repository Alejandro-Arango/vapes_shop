import importlib.util
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "verify_dependency_outage.py"
)
SPEC = importlib.util.spec_from_file_location(
    "verify_dependency_outage",
    SCRIPT_PATH,
)
outage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(outage)


class OutageHandler(BaseHTTPRequestHandler):
    readiness_status = 503
    readiness_payload = {
        "status": "error",
        "database": "unavailable",
        "cache": "not_checked",
    }

    def do_GET(self):
        if self.path == "/livez":
            body = b"ok\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            request_id = "liveness-request"
        else:
            body = json.dumps(type(self).readiness_payload).encode("utf-8")
            self.send_response(type(self).readiness_status)
            self.send_header("Content-Type", "application/json")
            request_id = "readiness-request"

        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Request-ID", request_id)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format_string, *args):
        return


class DependencyOutageVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            OutageHandler,
        )
        cls.thread = threading.Thread(
            target=cls.server.serve_forever,
            daemon=True,
        )
        cls.thread.start()
        host, port = cls.server.server_address
        cls.liveness_url = f"http://{host}:{port}/livez"
        cls.readiness_url = f"http://{host}:{port}/healthz"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        OutageHandler.readiness_status = 503
        OutageHandler.readiness_payload = {
            "status": "error",
            "database": "unavailable",
            "cache": "not_checked",
        }

    def test_database_outage_keeps_liveness_and_degrades_readiness(self):
        exit_code, report = outage.verify_database_outage(
            self.liveness_url,
            self.readiness_url,
            budget=5,
            interval=0,
            timeout=1,
            consecutive=2,
            allow_http=True,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], "degraded_as_expected")
        self.assertEqual(report["attempts"], 2)
        self.assertEqual(report["consecutive_successes"], 2)

    def test_incorrect_readiness_payload_is_rejected(self):
        OutageHandler.readiness_payload = {
            "status": "error",
            "database": "available",
            "cache": "unavailable",
        }

        with self.assertRaises(outage.MonitorError):
            outage.check_database_outage(self.readiness_url, timeout=1)

    def test_healthy_readiness_times_out_during_expected_outage(self):
        OutageHandler.readiness_status = 200
        OutageHandler.readiness_payload = {
            "status": "ok",
            "database": "available",
            "cache": "available",
        }
        times = iter((0.0, 0.0, 0.5, 1.1, 1.1))

        exit_code, report = outage.verify_database_outage(
            self.liveness_url,
            self.readiness_url,
            budget=1,
            interval=0,
            timeout=1,
            consecutive=1,
            allow_http=True,
            sleep=lambda _: None,
            monotonic=lambda: next(times),
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(report["status"], "timeout")

    def test_invalid_configuration_is_rejected(self):
        with self.assertRaises(outage.MonitorError):
            outage.verify_database_outage(
                self.liveness_url,
                self.readiness_url,
                budget=0,
                allow_http=True,
            )

    def test_report_file_is_written_with_restricted_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "dependency-report.json"

            with patch.object(outage.os, "chmod") as chmod:
                outage.write_report(report_path, {"status": "timeout"})

            chmod.assert_called_once_with(
                report_path.with_suffix(".json.tmp"),
                0o600,
            )
            self.assertEqual(
                json.loads(report_path.read_text(encoding="utf-8")),
                {"status": "timeout"},
            )

    def test_report_symlink_paths_are_rejected_before_write(self):
        for blocked_name in ("output", "parent", "temporary"):
            with self.subTest(blocked_name=blocked_name):
                with tempfile.TemporaryDirectory() as directory:
                    report_path = Path(directory) / "dependency-report.json"
                    temporary_path = report_path.with_suffix(".json.tmp")
                    blocked_path = {
                        "output": report_path,
                        "parent": report_path.parent,
                        "temporary": temporary_path,
                    }[blocked_name]

                    def is_symlink(path):
                        return path == blocked_path

                    with patch.object(outage.Path, "is_symlink", is_symlink):
                        with self.assertRaisesRegex(
                            outage.MonitorError,
                            "reporte de dependencia no admite enlaces simbolicos",
                        ):
                            outage.write_report(
                                report_path,
                                {"status": "timeout"},
                            )

                    self.assertFalse(report_path.exists())

    def test_existing_temporary_report_is_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "dependency-report.json"
            temporary_path = report_path.with_suffix(".json.tmp")
            temporary_path.write_text("stale\n", encoding="utf-8")

            with self.assertRaisesRegex(
                outage.MonitorError,
                "temporales preexistentes",
            ):
                outage.write_report(report_path, {"status": "timeout"})

            self.assertFalse(report_path.exists())
            self.assertEqual(
                temporary_path.read_text(encoding="utf-8"),
                "stale\n",
            )


if __name__ == "__main__":
    unittest.main()
