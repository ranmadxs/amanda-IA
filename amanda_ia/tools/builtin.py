"""Tools integradas: hora."""


def get_time() -> str:
    """Obtiene la hora actual del sistema.

    Returns:
        Hora actual formateada.
    """
    from datetime import datetime

    return datetime.now().strftime("%H:%M:%S - %d/%m/%Y")

