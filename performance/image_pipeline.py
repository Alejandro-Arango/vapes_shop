#!/usr/bin/env python3
"""
Valida normalizacion y escritura concurrente de imagenes en almacenamiento local.
No usa la base de datos ni conserva los archivos generados.
"""

import argparse
import json
import os
import re
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path


SAFE_PATH_PATTERN = re.compile(
    r"^store/img/products/[0-9a-f]{32}\.png$"
)
PRIVATE_MARKER = b"metadata-privada"
TRAILING_MARKER = b"<script>contenido-anexado</script>"


def configure_django():
    project_root = Path(
        os.environ.get(
            "DJANGO_PROJECT_ROOT",
            Path(__file__).resolve().parents[1] / "backend",
        )
    ).resolve()
    sys.path.insert(0, str(project_root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mi_tienda.settings")

    import django

    django.setup()


def ensure_enabled():
    if os.environ.get("IMAGE_PIPELINE_TEST_ENABLED", "").lower() != "true":
        raise RuntimeError(
            "Define IMAGE_PIPELINE_TEST_ENABLED=true para ejecutar la prueba."
        )


def build_upload_payload():
    from PIL import Image, PngImagePlugin

    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Comment", PRIVATE_MARKER.decode("ascii"))
    output = BytesIO()
    Image.new("RGB", (64, 64), color="white").save(
        output,
        format="PNG",
        pnginfo=metadata,
    )
    return output.getvalue() + TRAILING_MARKER


def write_report(path, payload):
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run_pipeline(workers, uploads):
    from django.core.files.storage import FileSystemStorage
    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    from store.models import product_image_upload_to, sanitize_product_image

    if workers < 1 or uploads < workers:
        raise RuntimeError("uploads debe ser mayor o igual que workers.")

    payload = build_upload_payload()

    with tempfile.TemporaryDirectory(prefix="image-pipeline-") as directory:
        storage = FileSystemStorage(location=directory)

        def store_upload(_):
            upload = SimpleUploadedFile(
                "../../producto.png",
                payload,
                content_type="image/png",
            )
            sanitized = sanitize_product_image(upload)
            target_name = product_image_upload_to(None, sanitized.name)
            return storage.save(target_name, sanitized)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            stored_names = list(executor.map(store_upload, range(uploads)))

        unique_names = set(stored_names)

        if len(unique_names) != uploads:
            raise RuntimeError("Se detectaron colisiones de nombres.")

        if not all(SAFE_PATH_PATTERN.fullmatch(name) for name in stored_names):
            raise RuntimeError("Se genero una ruta de imagen insegura.")

        for stored_name in stored_names:
            stored_path = Path(directory) / Path(stored_name)
            content = stored_path.read_bytes()

            if PRIVATE_MARKER in content or TRAILING_MARKER in content:
                raise RuntimeError("La normalizacion conservo datos no seguros.")

            with Image.open(stored_path) as image:
                image.load()

                if (
                    image.format != "PNG"
                    or image.size != (64, 64)
                    or getattr(image, "n_frames", 1) != 1
                ):
                    raise RuntimeError("Una imagen almacenada quedo invalida.")

        return {
            "bytes_per_input": len(payload),
            "stored_files": len(stored_names),
            "unique_names": len(unique_names),
            "workers": workers,
        }


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--uploads", type=int, default=100)
    parser.add_argument("--output", required=True)
    return parser


def main():
    arguments = build_parser().parse_args()
    configure_django()
    ensure_enabled()
    report = run_pipeline(arguments.workers, arguments.uploads)
    write_report(arguments.output, {"ok": True, **report})
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
