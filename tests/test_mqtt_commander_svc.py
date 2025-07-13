import pytest

# poetry run pytest tests/test_mqtt_commander_svc.py::test_get_mqtt_command -s
@pytest.mark.integration
def test_get_mqtt_command(mqtt_commander_svc):
    """Test de integración para verificar que get_mqtt_command funciona correctamente."""
    print("🧪 Iniciando test de MqttCommanderSvc...")
    
    # Test con un comando válido
    test_message = "enciende la bomba"
    response = mqtt_commander_svc.get_mqtt_command(test_message)
    
    print(f"📤 Mensaje de prueba: {test_message}")
    print(f"📥 Respuesta: {response}")
    
    # Verificar que la respuesta no esté vacía
    assert response is not None
    assert len(response) > 0
    
    # Verificar que si es un comando válido, contenga información JSON
    if "Comando no reconocido" not in response:
        assert "command" in response or "topic" in response
    
    print("✅ Test de MqttCommanderSvc completado exitosamente") 