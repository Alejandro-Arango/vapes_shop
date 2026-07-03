"""
Archivo: url_utils.py
Descripcion: Centraliza validaciones de URLs usadas fuera del backend.
Dependencias: urllib.parse
"""

from urllib.parse import urlsplit


SAFE_EXTERNAL_URL_SCHEMES = {"http", "https"}


def normalize_safe_external_url(value):
    """
    Nombre: normalize_safe_external_url
    Descripcion: Acepta solo URLs absolutas http/https para exponerlas fuera del backend.
    Retorna: URL segura sin espacios externos o cadena vacia.
    """
    url = (value or "").strip()

    if not url:
        return ""

    parsed_url = urlsplit(url)

    if (
        parsed_url.scheme.lower() not in SAFE_EXTERNAL_URL_SCHEMES
        or not parsed_url.netloc
    ):
        return ""

    return url
