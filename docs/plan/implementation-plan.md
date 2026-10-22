# RetailSmart — Implementation Plan

## Principio de ejecución

La implementación se hará por etapas cerrables.

```text
Arquitectura
   ↓
Contratos
   ↓
Infraestructura
   ↓
Pruebas unitarias de eventos
   ↓
Pipelines
   ↓
Productores paramétricos
   ↓
Batch / Predictivo / Consumo
```

La Arquitectura de Solución es la fuente de verdad.

---

# PASO 1 — Arquitectura y contratos

## Objetivo
Congelar la correspondencia entre diseño y código.

## Alcance
- architecture overview;
- mapping Arquitectura de Solución → implementación;
- contratos de streaming;
- matriz fuente → vertical.

## Definition of Done
- [ ] arquitectura actual versionada;
- [ ] 6 eventos streaming documentados;
- [ ] origen de cada evento identificado;
- [ ] utilidad de cada evento vinculada a vertical;
- [ ] no existen eventos implementados fuera del diseño.

---

# FASE 2 — Infraestructura GCP reproducible

## Objetivo
Crear el core RetailSmart mediante código/scripts, sin depender de creación manual.

## Alcance inicial
Streaming core:

- APIs requeridas;
- Cloud Pub/Sub:
  - Tópico Eventos Retail;
  - suscripciones;
  - Tópico Insights Retail;
- Cloud Storage:
  - Bronze;
  - Silver;
  - staging/temp si Dataflow lo requiere;
- BigQuery:
  - dataset Gold;
- IAM mínimo;
- configuración de región/proyecto.

## Reglas
- sin Terraform inicialmente;
- Python + `gcloud` / `bq` / utilitarios GCP;
- idempotencia;
- configuración externa;
- `deploy`, `validate`, `destroy`.

## Definition of Done
```bash
./scripts/deploy_streaming_core.sh
./scripts/validate_streaming_core.sh
```

debe dejar toda la infraestructura lista sin intervención manual.

---

# PASO 3 — Pruebas unitarias de eventos

## Objetivo
Validar contratos y conectividad de forma simple, evento por evento.

Ejemplos:

```bash
python -m producers.streaming.send_event --type clic_event
python -m producers.streaming.send_event --type stock_event
python -m producers.streaming.send_event --type location_event
```

## Alcance
- 1 evento a demanda;
- N eventos (diferido; FASE 3.2 publica únicamente uno por ejecución);
- validación JSON Schema;
- publicación en Tópico Eventos Retail;
- logs claros.

## Definition of Done
Cada uno de los 6 eventos puede generarse y publicarse de manera independiente.

---

# PASO 4 — Streaming E2E

## Objetivo

```text
Productor
→ Tópico Eventos Retail
→ Dataflow
→ Bronze
→ Silver
→ Procesamiento Tiempo Real
→ Tópico Insights Retail
→ Gold
```

## Primera iteración
Cerrar primero:

```text
Pub/Sub → Bronze → Stage 1 → Silver
```

Luego agregar:

```text
Stage 2 → Insights Retail → Gold
```

## Definition of Done
Existe una prueba E2E automática y repetible.

---

# PASO 5 — Producer Console

## Objetivo
Crear una plataforma de pruebas separada del core.

## Capacidades
- elegir tipo de evento;
- elegir cantidad;
- elegir velocidad;
- elegir escenario;
- generar eventos usando los mismos contratos y librerías del CLI.

## Escenarios
- NORMAL
- HIGH_DEMAND
- LOW_STOCK
- DELIVERY_DELAY
- TELEMETRY_ANOMALY
- WAREHOUSE_EQUIPMENT_DEGRADATION

## Regla
La consola no contiene lógica duplicada; reutiliza el generador base.

---

# PASOS POSTERIORES

Después de cerrar Streaming:

6. Batch reproducible
7. Forecast / Planificación
8. Mantenimiento predictivo
9. OLAP / Reporting
10. API / consumidores
11. Carga, resiliencia y costos
12. Demo y documentación final

---

# Trabajo paralelo

Una vez cerrada la fase 1:

### Track A — Infraestructura
Puede trabajar en la fase 2.

### Track B — Contratos / Test CLI
Puede desarrollar Paso 3 sobre mocks locales mientras infraestructura avanza.

### Track C — Producer Console
Puede diseñar la UI y lógica paramétrica, sin desplegar hasta estabilizar el generador base.

### Track D — Documentación / Validación
Mantiene matriz E2E, evidencia, README, pruebas y trazabilidad.

---

# Prompt base para Codex

Antes de modificar código, Codex debe leer:

```text
docs/architecture/architecture-overview.md
docs/architecture/implementation-mapping.md
docs/data/streaming-contracts.md
docs/data/source-to-vertical-matrix.md
docs/plan/implementation-plan.md
```

Reglas:

1. La Arquitectura de Solución es fuente de verdad.
2. No inventar eventos ni componentes.
3. No modificar contratos sin documentar decisión.
4. Trabajar únicamente en el paso solicitado.
5. Antes de programar, proponer:
   - archivos;
   - recursos;
   - comandos;
   - pruebas;
   - riesgos.
6. Priorizar simplicidad operativa, mantenibilidad y reproducibilidad.
7. Todo debe ser reproducible.

---

## Criterios para iniciar la implementación

Antes del desarrollo de la infraestructura GCP reproducible para el slice
Streaming, revisar los documentos de arquitectura, datos y plan. El plan de
implementación debe:

1. Resumir los componentes de arquitectura incluidos.
2. Identificar los recursos GCP correspondientes.
3. Definir la estructura mínima de archivos y las variables de configuración.
4. Especificar los comandos `deploy`, `validate` y `destroy`.
5. Identificar dependencias y permisos IAM mínimos.
6. Excluir Batch, ML, Looker y Producer Console del alcance.
7. Obtener revisión y aprobación antes de iniciar el desarrollo.
