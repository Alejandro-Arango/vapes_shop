import importlib.util
import io
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "monitor_production.py"
SPEC = importlib.util.spec_from_file_location("monitor_production", SCRIPT_PATH)
monitor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(monitor)


class MonitorHandler(BaseHTTPRequestHandler):
    readiness_status = 200
    readiness_payload = {
        "status": "ok",
        "database": "available",
        "cache": "available",
    }
    readiness_requests = 0
    webhook_requests = []

    def do_GET(self):
        type(self).readiness_requests += 1

        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/healthz")
            self.end_headers()
            return

        body = json.dumps(type(self).readiness_payload).encode("utf-8")
        self.send_response(type(self).readiness_status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Request-ID", "proxy-request-123")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length)
        type(self).webhook_requests.append(
            {
                "payload": json.loads(body.decode("utf-8")),
                "authorization": self.headers.get("Authorization"),
            }
        )
        self.send_response(204)
        self.end_headers()

    def log_message(self, format_string, *args):
        return


class ProductionMonitorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            MonitorHandler,
        )
        cls.thread = threading.Thread(
            target=cls.server.serve_forever,
            daemon=True,
        )
        cls.thread.start()
        host, port = cls.server.server_address
        cls.base_url = f"http://{host}:{port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        MonitorHandler.readiness_status = 200
        MonitorHandler.readiness_payload = {
            "status": "ok",
            "database": "available",
            "cache": "available",
        }
        MonitorHandler.readiness_requests = 0
        MonitorHandler.webhook_requests = []

    def test_healthy_readiness_succeeds_without_alert(self):
        exit_code, event = monitor.run_monitor(
            f"{self.base_url}/healthz",
            attempts=2,
            retry_delay=0,
            allow_http=True,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(event["status"], "ok")
        self.assertEqual(event["request_id"], "proxy-request-123")
        self.assertEqual(MonitorHandler.readiness_requests, 1)
        self.assertEqual(MonitorHandler.webhook_requests, [])

    def test_unhealthy_readiness_retries_and_sends_alert(self):
        MonitorHandler.readiness_status = 503
        MonitorHandler.readiness_payload = {
            "status": "error",
            "database": "unavailable",
            "cache": "not_checked",
        }

        exit_code, event = monitor.run_monitor(
            f"{self.base_url}/healthz",
            attempts=3,
            retry_delay=0,
            webhook_url=f"{self.base_url}/webhook",
            webhook_token="test-token",
            allow_http=True,
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(event["status"], "critical")
        self.assertEqual(event["alert"], "sent")
        self.assertEqual(MonitorHandler.readiness_requests, 3)
        self.assertEqual(len(MonitorHandler.webhook_requests), 1)
        alert = MonitorHandler.webhook_requests[0]
        self.assertEqual(alert["authorization"], "Bearer test-token")
        self.assertEqual(alert["payload"]["event"]["status"], "critical")
        self.assertIn("content", alert["payload"])
        self.assertIn("text", alert["payload"])

    def test_invalid_payload_is_reported_as_failure(self):
        MonitorHandler.readiness_payload = {
            "status": "ok",
            "database": "unavailable",
            "cache": "available",
        }

        exit_code, event = monitor.run_monitor(
            f"{self.base_url}/healthz",
            attempts=1,
            retry_delay=0,
            allow_http=True,
        )

        self.assertEqual(exit_code, 1)
        self.assertIn("database", event["error"])

    def test_http_is_rejected_without_explicit_local_override(self):
        with self.assertRaises(monitor.MonitorError):
            monitor.run_monitor(
                f"{self.base_url}/healthz",
                attempts=1,
            )

    def test_redirect_is_not_followed(self):
        exit_code, event = monitor.run_monitor(
            f"{self.base_url}/redirect",
            attempts=1,
            retry_delay=0,
            allow_http=True,
        )

        self.assertEqual(exit_code, 1)
        self.assertIn("HTTP 302", event["error"])
        self.assertEqual(MonitorHandler.readiness_requests, 1)

    def test_urls_with_credentials_or_query_are_rejected(self):
        invalid_urls = (
            "https://user:secret@example.com/healthz",
            "https://example.com/healthz?token=secret",
        )

        for invalid_url in invalid_urls:
            with self.subTest(url=invalid_url):
                with self.assertRaises(monitor.MonitorError):
                    monitor.run_monitor(
                        invalid_url,
                        attempts=1,
                    )

    def test_report_file_is_written_with_restricted_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "production-monitor.json"

            with patch.object(monitor.os, "chmod") as chmod:
                monitor.write_report(
                    report_path,
                    {"status": "ok", "event": "production_readiness"},
                )

            chmod.assert_called_once_with(
                report_path.with_suffix(".json.tmp"),
                0o600,
            )
            self.assertEqual(
                json.loads(report_path.read_text(encoding="utf-8")),
                {"status": "ok", "event": "production_readiness"},
            )

    def test_report_symlink_paths_are_rejected_before_write(self):
        for blocked_name in ("output", "parent", "temporary"):
            with self.subTest(blocked_name=blocked_name):
                with tempfile.TemporaryDirectory() as directory:
                    report_path = Path(directory) / "production-monitor.json"
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
                            monitor.MonitorError,
                            (
                                "reporte de monitoreo productivo no admite "
                                "enlaces simbolicos"
                            ),
                        ):
                            monitor.write_report(
                                report_path,
                                {
                                    "status": "ok",
                                    "event": "production_readiness",
                                },
                            )

                    self.assertFalse(report_path.exists())

    def test_configuration_error_is_persisted_to_report(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "production-monitor.json"
            arguments = [
                "monitor_production.py",
                "--url",
                "http://example.com/healthz",
                "--output",
                str(report_path),
            ]

            with patch.object(monitor.sys, "argv", arguments):
                with patch.object(monitor.sys, "stderr", io.StringIO()):
                    exit_code = monitor.main()

            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 2)
        self.assertEqual(report["status"], "configuration_error")
        self.assertIn("HTTPS", report["error"])


if __name__ == "__main__":
    unittest.main()
