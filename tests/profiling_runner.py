import subprocess
import os
from .profiling_config import (
    is_profiling_enabled,
    create_profiling_directory,
    get_full_profiling_path
)

def run_profiled_tests():
    """
    Ejecuta los tests con profiling habilitado usando pyinstrument.
    Solo se ejecuta si ENABLE_PROFILING está habilitado.
    """
    if not is_profiling_enabled():
        print("⚠️ Profiling deshabilitado. Para habilitarlo, configura ENABLE_PROFILING=true")
        return
    
    print("🔍 Ejecutando tests con profiling habilitado...")
    
    # Crear directorio de profiling
    create_profiling_directory()
    
    # Generar rutas de archivos
    html_report = get_full_profiling_path("test_report", "html")
    json_report = get_full_profiling_path("results", "json")
    pyinstrument_report = get_full_profiling_path("pyinstrument", "html")
    
    print(f"📊 HTML Report: {html_report}")
    print(f"📋 JSON Report: {json_report}")
    print(f"🔍 PyInstrument Report: {pyinstrument_report}")
    
    # Comando pyinstrument con pytest como subcomando
    cmd = [
        "python", "-m", "pyinstrument",
        "-r", "html",
        "-o", pyinstrument_report,
        "-m", "pytest",
        "--durations=0",
        f"--html={html_report}",
        "--json-report",
        f"--json-report-file={json_report}"
    ]
    
    # Ejecutar pyinstrument con pytest
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"✅ Profiling completado exitosamente!")
            print(f"📊 HTML: {html_report}")
            print(f"📋 JSON: {json_report}")
            print(f"🔍 PyInstrument: {pyinstrument_report}")
        else:
            print(f"❌ Error durante el profiling:")
            print(result.stderr)
            
    except Exception as e:
        print(f"❌ Error ejecutando profiling: {str(e)}")

def run_simple_profiling():
    """
    Ejecuta profiling simple sin pyinstrument.
    """
    if not is_profiling_enabled():
        print("⚠️ Profiling deshabilitado. Para habilitarlo, configura ENABLE_PROFILING=true")
        return
    
    print("🔍 Ejecutando profiling simple...")
    
    # Crear directorio de profiling
    create_profiling_directory()
    
    # Generar rutas de archivos
    html_report = get_full_profiling_path("test_report", "html")
    json_report = get_full_profiling_path("results", "json")
    
    print(f"📊 HTML Report: {html_report}")
    print(f"📋 JSON Report: {json_report}")
    
    # Comando pytest simple
    cmd = [
        "pytest",
        "--durations=0",
        f"--html={html_report}",
        "--json-report",
        f"--json-report-file={json_report}"
    ]
    
    # Ejecutar pytest
    subprocess.run(cmd)

if __name__ == "__main__":
    run_simple_profiling() 