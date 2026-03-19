"""Tools integradas: temperatura, hora, etc."""


def get_temperature(city: str = "") -> str:
    """Obtiene la temperatura actual de una ciudad.

    Args:
        city: Nombre de la ciudad (opcional). Si está vacío, devuelve temperatura genérica.

    Returns:
        Temperatura en °C.
    """
    temperatures = {
        "santiago": "22°C",
        "buenos aires": "18°C",
        "lima": "24°C",
        "bogotá": "19°C",
        "madrid": "16°C",
        "new york": "14°C",
        "londres": "12°C",
        "tokio": "20°C",
    }
    if city:
        key = city.lower().strip()
        return temperatures.get(key, f"Temperatura simulada: 21°C (ciudad '{city}' no en base)")
    return "Temperatura simulada: 21°C"


def get_time() -> str:
    """Obtiene la hora actual del sistema.

    Returns:
        Hora actual formateada.
    """
    from datetime import datetime

    return datetime.now().strftime("%H:%M:%S - %d/%m/%Y")
