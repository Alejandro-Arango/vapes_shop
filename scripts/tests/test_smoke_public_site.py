import importlib.util
import io
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "smoke_public_site.py"
SPEC = importlib.util.spec_from_file_location("smoke_public_site", SCRIPT_PATH)
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Content-Security-Policy": (
        "default-src 'self'; object-src 'none'; "
        "frame-ancestors 'none'; script-src 'self'; connect-src 'self'"
    ),
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Referrer-Policy": "same-origin",
}


class PublicSiteHandler(BaseHTTPRequestHandler):
    health_payload = {
        "status": "ok",
        "database": "available",
        "cache": "available",
    }
    health_status = 200
    home_headers = SECURITY_HEADERS.copy()
    home_body = (
        "<!doctype html><title>Vape Shop - Tienda</title>"
        "<main id='product-list'></main><form id='contact-form'></form>"
    )
    redirect_liveness = False

    def do_GET(self):
        if self.path == "/livez":
            self.handle_liveness()
            return

        if self.path == "/healthz":
            self.handle_readiness()
            return

        if self.path == "/":
            self.handle_home()
            return

        self.send_response(404)
        self.end_headers()

    def handle_liveness(self):
        if type(self).redirect_liveness:
            self.send_response(302)
            self.send_header("Location", "/livez")
            self.send_header("X-Request-ID", "live-redirect")
            self.end_headers()
            return

        body = b"ok\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Request-ID", "live-request")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def handle_readiness(self):
        body = json.dumps(type(self).health_payload).encode("utf-8")
        self.send_response(type(self).health_status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Request-ID", "health-request")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def handle_home(self):
        body = type(self).home_body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Request-ID", "home-request")
        for name, value in type(self).home_headers.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format_string, *args):
        return


class PublicSiteSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            PublicSiteHandler,
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
        PublicSiteHandler.health_payload = {
            "status": "ok",
            "database": "available",
            "cache": "available",
        }
        PublicSiteHandler.health_status = 200
        PublicSiteHandler.home_headers = SECURITY_HEADERS.copy()
        PublicSiteHandler.home_body = (
            "<!doctype html><title>Vape Shop - Tienda</title>"
            "<main id='product-list'></main><form id='contact-form'></form>"
        )
        PublicSiteHandler.redirect_liveness = False

    def test_healthy_public_site_succeeds(self):
        exit_code, report = smoke.run_smoke(
            self.base_url,
            allow_http=True,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(
            [check["name"] for check in report["checks"]],
            ["liveness", "readiness", "home"],
        )
        self.assertTrue(
            all(check["status"] == "ok" for check in report["checks"])
        )

    def test_http_base_url_requires_explicit_local_override(self):
        with self.assertRaisesRegex(smoke.SmokeError, "HTTPS"):
            smoke.run_smoke(self.base_url)

    def test_readiness_unhealthy_marks_smoke_as_critical(self):
        PublicSiteHandler.health_payload = {
            "status": "ok",
            "database": "unavailable",
            "cache": "available",
        }

        exit_code, report = smoke.run_smoke(
            self.base_url,
            allow_http=True,
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(report["status"], "critical")
        readiness = next(
            check
            for check in report["checks"]
            if check["name"] == "readiness"
        )
        self.assertIn("database", readiness["error"])

    def test_redirects_are_not_followed(self):
        PublicSiteHandler.redirect_liveness = True

        exit_code, report = smoke.run_smoke(
            self.base_url,
            allow_http=True,
        )

        self.assertEqual(exit_code, 1)
        liveness = next(
            check
            for check in report["checks"]
            if check["name"] == "liveness"
        )
        self.assertIn("HTTP 302", liveness["error"])

    def test_missing_security_header_marks_home_as_critical(self):
        PublicSiteHandler.home_headers = SECURITY_HEADERS.copy()
        PublicSiteHandler.home_headers.pop("Content-Security-Policy")

        exit_code, report = smoke.run_smoke(
            self.base_url,
            allow_http=True,
        )

        self.assertEqual(exit_code, 1)
        home = next(
            check
            for check in report["checks"]
            if check["name"] == "home"
        )
        self.assertIn("Content-Security-Policy", home["error"])

    def test_hsts_is_required_when_enabled(self):
        exit_code, report = smoke.run_smoke(
            self.base_url,
            allow_http=True,
            require_hsts=True,
        )

        self.assertEqual(exit_code, 1)
        home = next(
            check
            for check in report["checks"]
            if check["name"] == "home"
        )
        self.assertIn("Strict-Transport-Security", home["error"])

    def test_base_url_rejects_paths_queries_and_credentials(self):
        invalid_urls = (
            f"{self.base_url}/admin/",
            f"{self.base_url}?token=abc",
            "http://user:secret@127.0.0.1/",
        )

        for invalid_url in invalid_urls:
            with self.subTest(url=invalid_url):
                with self.assertRaises(smoke.SmokeError):
                    smoke.run_smoke(invalid_url, allow_http=True)

    def test_report_file_is_written_with_restricted_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "public-smoke.json"

            with patch.object(smoke.os, "chmod") as chmod:
                smoke.write_report(
                    report_path,
                    {"event": "public_site_smoke", "status": "ok"},
                )

            chmod.assert_called_once_with(
                report_path.with_suffix(".json.tmp"),
                0o600,
            )
            self.assertEqual(
                json.loads(report_path.read_text(encoding="utf-8")),
                {"event": "public_site_smoke", "status": "ok"},
            )

    def test_existing_temporary_report_is_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "public-smoke.json"
            temporary_path = report_path.with_suffix(".json.tmp")
            temporary_path.write_text("stale\n", encoding="utf-8")

            with self.assertRaisesRegex(
                smoke.SmokeError,
                "temporales preexistentes",
            ):
                smoke.write_report(
                    report_path,
                    {"event": "public_site_smoke", "status": "ok"},
                )

            self.assertFalse(report_path.exists())

    def test_configuration_error_is_persisted_to_report(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "public-smoke.json"
            arguments = [
                "smoke_public_site.py",
                "--url",
                self.base_url,
                "--output",
                str(report_path),
            ]

            with patch.object(smoke.sys, "argv", arguments):
                with patch.object(smoke.sys, "stderr", io.StringIO()):
                    exit_code = smoke.main()

            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 2)
        self.assertEqual(report["status"], "configuration_error")
        self.assertIn("HTTPS", report["error"])


if __name__ == "__main__":
    unittest.main()
