import subprocess
import os
from datetime import datetime

def generate_test_report():
    """
    Genera un reporte de pytest con formato de fecha dinámico
    """
    # Crear directorio target/test-report si no existe
    os.makedirs("target/test-report", exist_ok=True)
    
    # Generar timestamp con formato YYYY_MM_DD_HH_MM_SS
    timestamp = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
    
    # Comando pytest con reportes
    cmd = [
        "pytest",
        "--durations=0",
        f"--html=target/test-report/test_report_{timestamp}.html",
        "--json-report",
        f"--json-report-file=target/test-report/results_{timestamp}.json"
    ]
    
    # Ejecutar pytest
    subprocess.run(cmd)

if __name__ == "__main__":
    generate_test_report() 