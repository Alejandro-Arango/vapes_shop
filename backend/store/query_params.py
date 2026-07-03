"""
Archivo: query_params.py
Descripcion: Utilidades para validar parametros query acotados y evitar conversiones ambiguas.
"""


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
