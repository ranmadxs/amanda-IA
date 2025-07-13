import os
from datetime import datetime

def is_profiling_enabled():
    """
    Verifica si el profiling está habilitado a través de una variable de entorno.
    Por defecto está habilitado. Configura 'ENABLE_PROFILING' a 'false' o '0' para deshabilitarlo.
    """
    return os.getenv('ENABLE_PROFILING', 'true').lower() not in ('false', '0')

def get_profiling_output_path():
    """
    Obtiene la ruta base para los archivos de reporte de profiling.
    """
    return os.getenv('PROFILING_OUTPUT_PATH', 'target/profiling/')

def get_profiling_timestamp():
    """
    Genera un timestamp para los archivos de profiling.
    """
    return datetime.now().strftime('%Y_%m_%d_%H_%M_%S')

def get_profiling_filename(prefix="profile", extension="html"):
    """
    Genera un nombre de archivo para profiling con timestamp.
    
    Args:
        prefix: Prefijo del archivo (default: "profile")
        extension: Extensión del archivo (default: "html")
    
    Returns:
        str: Nombre del archivo con timestamp
    """
    timestamp = get_profiling_timestamp()
    return f"{prefix}_{timestamp}.{extension}"

def get_full_profiling_path(prefix="profile", extension="html"):
    """
    Obtiene la ruta completa para un archivo de profiling.
    
    Args:
        prefix: Prefijo del archivo
        extension: Extensión del archivo
    
    Returns:
        str: Ruta completa del archivo
    """
    output_path = get_profiling_output_path()
    filename = get_profiling_filename(prefix, extension)
    return os.path.join(output_path, filename)

def create_profiling_directory():
    """
    Crea el directorio de profiling si no existe.
    """
    output_path = get_profiling_output_path()
    os.makedirs(output_path, exist_ok=True)
    return output_path 