#!/usr/bin/env python3
"""
Rechaza archivos secretos rastreados y marcadores de claves privadas.
Complementa Gitleaks con reglas simples que pueden ejecutarse sin dependencias.
"""

import re
import subprocess
import sys
from pathlib import Path, PurePosixPath


ALLOWED_EXAMPLE_NAMES = {
    ".env.example",
    "compose.env.example",
    "compose.production.env.example",
}
FORBIDDEN_NAMES = {
    ".env",
    ".env.local",
    "compose.env",
    "compose.production.env",
    "credentials.json",
    "service-account.json",
    "id_rsa",
    "id_ed25519",
}
FORBIDDEN_SUFFIXES = (
    ".key",
    ".p12",
    ".pfx",
    ".pem",
)
CONTENT_MARKERS = (
    re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bghp_[A-Za-z0-9]{36,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{60,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    re.compile(r"\bsk_live_[0-9A-Za-z]{20,}\b"),
)
MAX_TEXT_FILE_BYTES = 2 * 1024 * 1024


def list_tracked_files(project_root):
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=project_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if completed.returncode != 0:
        error = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"No fue posible consultar Git: {error}")

    return [
        PurePosixPath(item.decode("utf-8"))
        for item in completed.stdout.split(b"\0")
        if item
    ]


def is_forbidden_path(relative_path):
    name = relative_path.name.lower()

    if name in ALLOWED_EXAMPLE_NAMES:
        return False

    if name in FORBIDDEN_NAMES:
        return True

    return any(name.endswith(suffix) for suffix in FORBIDDEN_SUFFIXES)


def find_content_marker(content):
    for marker in CONTENT_MARKERS:
        if marker.search(content):
            return marker.pattern

    return None


def scan_tracked_files(project_root, tracked_files):
    findings = []

    for relative_path in tracked_files:
        if is_forbidden_path(relative_path):
            findings.append(
                f"archivo sensible rastreado: {relative_path.as_posix()}"
            )
            continue

        absolute_path = project_root.joinpath(*relative_path.parts)

        try:
            if absolute_path.stat().st_size > MAX_TEXT_FILE_BYTES:
                continue

            content = absolute_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        marker = find_content_marker(content)

        if marker:
            findings.append(
                f"marcador de credencial en {relative_path.as_posix()}: {marker}"
            )

    return findings


def main():
    project_root = Path(__file__).resolve().parents[1]

    try:
        tracked_files = list_tracked_files(project_root)
        findings = scan_tracked_files(project_root, tracked_files)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if findings:
        print("Se detectaron posibles secretos:", file=sys.stderr)

        for finding in findings:
            print(f"- {finding}", file=sys.stderr)

        return 1

    print("No hay archivos secretos rastreados ni marcadores conocidos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
