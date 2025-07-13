import os
import sys
from datetime import datetime
from pyinstrument import Profiler
import pytest
from .profiling_config import (
    create_profiling_directory,
    get_profiling_timestamp,
    get_profiling_output_path,
    is_profiling_enabled
)

def run_pytest_programmatically():
    """
    Ejecuta pytest programáticamente sin comandos del sistema
    """
    # Crear directorio usando la configuración centralizada
    create_profiling_directory()
    
    # Generar timestamp usando la configuración centralizada
    timestamp = get_profiling_timestamp()
    output_path = get_profiling_output_path()
    
    # Generar rutas de archivos
    html_report = f"{output_path}test_report_{timestamp}.html"
    json_report = f"{output_path}results_{timestamp}.json"
    
    print(f"📊 HTML Report: {html_report}")
    print(f"📋 JSON Report: {json_report}")
    
    # Configurar argumentos de pytest programáticamente
    pytest_args = [
        "--durations=0",
        f"--html={html_report}",
        "--json-report",
        f"--json-report-file={json_report}",
        "tests/"  # Directorio de tests
    ]
    
    # Ejecutar pytest programáticamente
    exit_code = pytest.main(pytest_args)
    return exit_code == 0

def generate_test_report():
    """
    Genera un reporte de pytest con profiling avanzado siempre habilitado
    """
    print("🔍 Ejecutando reporte de tests con profiling avanzado...")
    
    # --- Lógica de profiling siempre habilitado ---
    print("Profiling con Pyinstrument habilitado. Generando reporte...")
    profiler = Profiler()
    profiler.start()

    # Aquí va la ejecución de los tests
    success = run_pytest_programmatically()

    profiler.stop()

    # Generar el reporte HTML
    output_path = get_profiling_output_path()
    os.makedirs(output_path, exist_ok=True)  # Crea el directorio si no existe

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    html_report_filename = os.path.join(output_path, f"pyinstrument_report_{timestamp}.html")

    with open(html_report_filename, 'w') as f:
        f.write(profiler.output_html())
    print(f"Reporte HTML de Pyinstrument guardado en: {html_report_filename}")
    
    if success:
        print("✅ Tests completados exitosamente con profiling")
    else:
        print("❌ Algunos tests fallaron")

if __name__ == "__main__":
    generate_test_report() 