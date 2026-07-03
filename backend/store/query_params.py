"""
Archivo: query_params.py
Descripcion: Utilidades para validar parametros query acotados y evitar conversiones ambiguas.
"""


MAX_MODEL_ID = 9223372036854775807


def parse_bounded_positive_int(value, maximum):
    """
    Nombre: parse_bounded_positive_int
    Descripcion: Convierte un parametro query a entero positivo dentro de un limite seguro.
    Retorna: Entero valido o None cuando el valor no es aceptable.
    """
    if value is None:
        return None

    raw_value = str(value).strip()

    if (
        not raw_value
        or not raw_value.isascii()
        or not raw_value.isdecimal()
        or len(raw_value) > len(str(maximum))
    ):
        return None

    parsed_value = int(raw_value)

    if parsed_value < 1 or parsed_value > maximum:
        return None

    return parsed_value


def parse_bounded_query_text(value, maximum):
    """
    Nombre: parse_bounded_query_text
    Descripcion: Normaliza texto de query params y rechaza valores excesivos o de control.
    Retorna: Texto limpio, cadena vacia si no existe o None si no es aceptable.
    """
    if value is None:
        return ""

    raw_value = str(value).strip()

    if len(raw_value) > maximum or any(
        character in raw_value for character in ("\x00", "\r", "\n")
    ):
        return None

    return raw_value
