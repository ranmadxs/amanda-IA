# DPO — Direct Preference Optimization

## ¿Qué es?

DPO es la técnica estándar para afinar un modelo de lenguaje basándose en preferencias humanas. En lugar de decirle al modelo "esta respuesta tiene 8/10 puntos", le muestras pares de respuestas y le dices cuál preferiste. El modelo ajusta sus pesos para dar más probabilidad a la respuesta elegida y menos a la rechazada.

Es la técnica detrás de cómo se entrena el RLHF simplificado — sin necesitar un modelo de recompensa separado.

---

## Formato del dataset

El dataset es un archivo `.jsonl` donde cada línea es un JSON con tres campos:

```jsonl
{"prompt": "¿Qué temperatura tiene Santiago hoy?", "chosen": "Voy a consultar el sensor...", "rejected": "No tengo acceso a datos en tiempo real."}
{"prompt": "Lista los archivos de esta carpeta", "chosen": "Usando el tool filesystem: ls /ruta...", "rejected": "No puedo acceder al sistema de archivos."}
```

| Campo      | Descripción                                           |
|------------|-------------------------------------------------------|
| `prompt`   | El mensaje del usuario (o el historial completo)      |
| `chosen`   | La respuesta que se considera correcta / preferida    |
| `rejected` | La respuesta que el modelo dio y no fue satisfactoria |

---

## Herramientas recomendadas

### Unsloth (recomendado para hardware limitado)
- Optimizado para correr en una sola GPU con poca VRAM (8–16 GB)
- Soporte para Llama 3, Mistral, Phi, Qwen, etc.
- Integración con Hugging Face datasets
- Instalación: `pip install unsloth`
- Repositorio: [github.com/unslothai/unsloth](https://github.com/unslothai/unsloth)

### Axolotl (más flexible, más configuración)
- Config via YAML, soporta múltiples técnicas (SFT, DPO, LoRA, QLoRA)
- Pensado para entrenamientos más serios / multi-GPU
- Instalación: `pip install axolotl`
- Repositorio: [github.com/axolotl-org/axolotl](https://github.com/axolotl-org/axolotl)

---

## Flujo completo

```
1. Recopilar ejemplos
   └── Registrar prompts donde el modelo falló
   └── Escribir la respuesta "correcta" manualmente

2. Crear el dataset
   └── Formato .jsonl con prompt / chosen / rejected
   └── Mínimo recomendado: ~200-500 pares para resultados notables

3. Entrenar con LoRA (no fine-tuning completo)
   └── LoRA modifica solo una fracción de los pesos (~1-5%)
   └── Mucho más rápido y requiere menos VRAM

4. Exportar y convertir a GGUF
   └── Herramienta: llama.cpp convert_hf_to_gguf.py
   └── Cuantizar: Q4_K_M (buen balance calidad/tamaño)

5. Cargar en Ollama
   └── Crear un Modelfile que apunte al .gguf
   └── ollama create amanda-dpo -f Modelfile
   └── Probar: ollama run amanda-dpo
```

---

## Requisitos de hardware

| Modelo base   | VRAM mínima (LoRA Q4) | VRAM cómoda |
|---------------|----------------------|-------------|
| 7B parámetros | 8 GB                 | 12–16 GB    |
| 13B parámetros| 16 GB                | 24 GB       |
| 70B parámetros| No viable en consumer| 80+ GB      |

> Para llama3.1:8b (el modelo actual de amanda-IA), una GPU con 8–12 GB de VRAM es suficiente usando LoRA + cuantización.

---

## Pros y Contras

| Pros | Contras |
|------|---------|
| Cambia el comportamiento de forma permanente | Requiere GPU (no funciona bien en CPU) |
| No necesita modelo de recompensa separado | Hay que curar los datos manualmente |
| Compatible con LoRA (eficiente en VRAM) | Puede introducir regression en otras áreas |
| El resultado se puede usar directamente en Ollama | Requiere conocimiento básico de Python |

---

## Integración con amanda-IA

Para recopilar pares DPO directamente desde el agente, se podría añadir:

1. Un comando `/feedback bad` / `/feedback good` que guarde el último par prompt/response en un archivo `.jsonl`
2. Un script de postproceso que formatee esos logs al formato DPO
3. Un workflow de entrenamiento periódico (e.g., una vez por semana con los nuevos ejemplos)

El dataset acumulado quedaría en `.aia/dpo/feedback.jsonl`.
