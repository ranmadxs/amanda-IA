# Benchmark: ranmadxs (M1 Pro) vs localhost (M4)

Comparativa de rendimiento para AIA / Ollama entre las dos máquinas disponibles.

---

## Hardware

| Métrica                     | ranmadxs (M1 Pro)     | localhost (M4)        |
|-----------------------------|----------------------|-----------------------|
| Chip                        | Apple M1 Pro         | Apple M4              |
| CPU cores                   | 8 (6P + 2E)          | 10 (4P + 6E)          |
| RAM total                   | 16 GB                | 24 GB                 |
| **Bandwidth memoria**       | **~200 GB/s**        | **~120 GB/s**         |
| Neural Engine               | 11 TOPS              | 38 TOPS               |
| GPU cores                   | 14                   | 10                    |

---

## Ollama — qwen2.5:14b

El cuello de botella en inferencia LLM es el bandwidth de memoria (mover los pesos del modelo en cada token). Por eso el **M1 Pro gana en velocidad de tokens** a pesar de ser más viejo.

> Medición real — 300 tokens, mismo prompt en ambas máquinas simultáneamente.

### Ronda 1 — modelo en frío (localhost sin calentar)

| Métrica                        | ranmadxs (M1 Pro) | localhost (M4) | Ventaja       |
|--------------------------------|-------------------|----------------|---------------|
| Tokens/segundo (generación)    | 13.2 tok/s        | 11.3 tok/s     | 🔴↓ ranmadxs  |
| Prompt eval (tok/s)            | 21.9 tok/s        | 67.6 tok/s     | 🟢↑ localhost |
| Carga del modelo               | 136 ms            | 19 629 ms      | 🔴↓ ranmadxs  |
| Duración total (300 tokens)    | 26.4 s            | 47.2 s         | 🔴↓ ranmadxs  |

### Ronda 2 — modelo caliente en RAM en ambas máquinas

| Métrica                        | ranmadxs (M1 Pro) | localhost (M4) | Ventaja       |
|--------------------------------|-------------------|----------------|---------------|
| **Tokens/segundo (generación)**| **13.2 tok/s**    | **11.4 tok/s** | 🔴↓ ranmadxs  |
| Prompt eval (tok/s)            | 37.6 tok/s        | 128.6 tok/s    | 🟢↑ localhost |
| Carga del modelo               | 127 ms            | 90 ms          | ➡️            |
| **Duración total (300 tokens)**| **25.0 s**        | **27.1 s**     | 🔴↓ ranmadxs  |

### Ronda 3 — prompt corto con streaming ("hola como te llamas tu")

Mide cuándo aparece el **primer token visible** en pantalla — el tiempo real que percibe el usuario.

| Métrica                     | ranmadxs (M1 Pro) | localhost (M4) | Ventaja       |
|-----------------------------|-------------------|----------------|---------------|
| **Tiempo primer token (TTFT)** | **2 892 ms**   | **2 460 ms**   | 🟢↑ localhost |
| Duración total              | 5.51 s            | 5.54 s         | ➡️            |
| Tokens/segundo              | 13.5 tok/s        | 11.7 tok/s     | 🔴↓ ranmadxs  |

> El M4 procesa el prompt más rápido (mejor prompt eval), por lo que el usuario
> ve la respuesta ~430 ms antes. Una vez generando, ranmadxs es más rápido pero
> la duración total es idéntica para respuestas cortas.

---

## RAM — capacidad de modelos

| Modelo             | Tamaño aprox. | ranmadxs (16 GB) | localhost (24 GB) |
|--------------------|---------------|------------------|-------------------|
| qwen2.5:7b         | ~4.7 GB       | ✅ holgado        | ✅ holgado         |
| qwen2.5:14b        | ~9.0 GB       | ✅ ajustado       | ✅ holgado         |
| llama3.1:8b        | ~4.9 GB       | ✅ holgado        | ✅ holgado         |
| qwen2.5:32b (q4)   | ~20 GB        | ❌               | ⚠️ posible        |
| llama3.3:70b (q4)  | ~40 GB        | ❌               | ❌                |

---

## Conclusión para AIA

| Caso de uso                         | Mejor máquina  | Razón                                      |
|-------------------------------------|----------------|--------------------------------------------|
| Velocidad de respuesta (tok/s)      | **ranmadxs**   | 13.2 vs 11.3 tok/s (+17%)                  |
| Duración total por respuesta        | **ranmadxs**   | 26.4 s vs 47.2 s (casi el doble más rápido)|
| Carga en frío del modelo            | **ranmadxs**   | 136 ms vs 19 s (modelo ya en memoria)      |
| Prompt eval / contexto largo        | **localhost**  | 67.6 vs 21.9 tok/s (3x más rápido)        |
| Modelos grandes (>16 GB)            | **localhost**  | 24 GB RAM disponibles                      |
| Eficiencia energética               | **localhost**  | M4 consume menos watts por TOPS            |

**El M4 base no mejora al M1 Pro para AIA en el día a día.** La diferencia en tok/s es
pequeña (+17%) pero la carga en frío y la duración total son muy superiores en ranmadxs
porque el modelo ya estaba en memoria. El salto real vendría con un M4 Pro (273 GB/s)
o M4 Max (546 GB/s).

---

## Cómo medir

Para obtener tok/s reales en cualquiera de las dos máquinas:

```bash
# En ranmadxs
ssh ranmadxs '/usr/local/bin/ollama run qwen2.5:14b "Explica transformers en detalle"'

# Métricas detalladas vía API
curl -s http://localhost:11434/api/generate \
  -d '{"model":"qwen2.5:14b","prompt":"Explica transformers","stream":false}' \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)
tps = d['eval_count'] / (d['eval_duration'] / 1e9)
print(f\"tok/s: {tps:.1f}  |  tokens: {d['eval_count']}  |  total: {d['total_duration']/1e9:.1f}s\")
"
```

Para ranmadxs vía túnel SSH:

```bash
ssh -N -L 11435:localhost:11434 ranmadxs &
curl -s http://localhost:11435/api/generate \
  -d '{"model":"qwen2.5:14b","prompt":"Explica transformers","stream":false}' \
  | python3 -c "..."
kill %1
```
