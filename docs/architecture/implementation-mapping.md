# RetailSmart — Architecture to Implementation Mapping

## Objetivo

Mantener trazabilidad directa entre el diseño de la Arquitectura de Solución y el código.

> **Regla:** si un recurso o servicio no puede vincularse con un componente del diseño, no debe incorporarse sin una decisión arquitectónica explícita.

---

## Streaming

| Componente de solución | Tipo lógico | Implementación objetivo GCP | Artefacto de código esperado |
|---|---|---|---|
| Tópico Eventos Retail | Event bus | Cloud Pub/Sub Topic | `infra/pubsub/` |
| Ingesta Streaming | Ingesta | Pub/Sub + suscripción | `infra/pubsub/` |
| [Stream Processor] Ingesta Streaming | Stream processor | Apache Beam sobre Dataflow | `pipelines/streaming/` |
| Raw Event Writer | Writer lógico | salida del pipeline | `pipelines/streaming/` |
| Bronze Eventos Raw | Data Object | Cloud Storage | `infra/storage/` |
| Silver Event Writer | Writer lógico | salida del pipeline | `pipelines/streaming/` |
| Silver Eventos Curados | Data Object | Cloud Storage | `infra/storage/` |
| [Stream Processor] Procesamiento Tiempo Real | Stream processor | Apache Beam sobre Dataflow | `pipelines/streaming/` |
| Tópico Insights Retail | Event bus | Cloud Pub/Sub Topic | `infra/pubsub/` |
| Gold Insights Writer | Writer lógico | pipeline / sink | `pipelines/streaming/` |
| Gold Insights Retail | Data Product | BigQuery | `infra/bigquery/` |

---

## Productor unitario — FASE 3.2

Las seis fuentes lógicas de entrada se ejercitan mediante
`producers/streaming/send_event.py`. `build_event.py` construye muestras sintéticas
sin leer ejemplos; `publish.py` adapta gcloud y la identidad OPERATOR_ACCOUNT.
Reutiliza el validador oficial y publica únicamente en RS-STR-001. No crea recursos
GCP, cambia IAM, consume mensajes ni implementa procesamiento downstream.

## Eventos streaming

FASE 3.1: los seis contratos usan `contracts/streaming/common-event.schema.json`.
La validación estructural y semántica local está en
`contracts/streaming/validation.py`; los ejemplos son artefactos de prueba,
no productores. El detalle de campos y verticales está en
[contratos](../data/streaming-contracts.md) y [matriz](../data/source-to-vertical-matrix.md).

| Arquitectura | Origen | Contrato |
|---|---|---|
| `clic_event` | Aplicaciones de Canal (Web / App / POS) | `contracts/streaming/clic_event.schema.json` |
| `iot_event` | Sensores IoT de Tienda | `contracts/streaming/iot_event.schema.json` |
| `stock_event` | Estantería Inteligente | `contracts/streaming/stock_event.schema.json` |
| `location_event` | Tracking Logístico | `contracts/streaming/location_event.schema.json` |
| `telemetry_event` | Cámaras Frigoríficas | `contracts/streaming/telemetry_event.schema.json` |
| `warehouse_sensor_event` | Sensores de Almacén | `contracts/streaming/warehouse_sensor_event.schema.json` |

Eventos internos existentes en el diseño:
- `*_event`
- `valid_event`
- `curated_event`
- `clean_event`
- `insight_event`

Estos nombres deben conservarse cuando corresponda o documentarse si se ajustan.

---

## Batch

| Componente de solución | Implementación objetivo |
|---|---|
| [Batch Job] Ingesta Batch | Storage Transfer / scripts de carga |
| Bronze Datos Batch | Cloud Storage |
| [Batch Processor] Curación Batch | Spark / PySpark |
| Silver Datos Curados | Cloud Storage |
| [Orchestrator] Planificador Batch | Airflow / servicio gestionado de GCP por evaluar |
| [ML Job] Entrenamiento Forecast | Spark / PySpark |
| [Model] Modelo de Demanda | artefacto de modelo |
| [Batch Processor] Planificación Diaria | Spark / PySpark |
| Gold Planes Inventario | BigQuery |
| Procesamiento Analítico / OLAP | SQL / BigQuery |
| Gold Operational Mart | BigQuery |

---

## Mantenimiento predictivo

| Componente de solución | Implementación objetivo |
|---|---|
| [ML Job] Entrenamiento Mantenimiento Predictivo | Spark / PySpark |
| [Model] Modelo Mantenimiento Predictivo | artefacto versionado |
| [Stream Processor] Análisis de Telemetría y Mantenimiento Predictivo | procesamiento streaming |
| Gold Maintenance Insights | BigQuery |

---

## Exposición

| Capacidad | Implementación objetivo |
|---|---|
| Consumo asíncrono de insights | Pub/Sub subscription |
| Consulta de productos Gold | API REST |
| Runtime API | Cloud Run |
| BI / Reporting | Looker + BigQuery |

---

## Convenciones

- No hardcodear `PROJECT_ID`, región, bucket, dataset o tópicos.
- Configuración por variables de entorno / archivos de configuración.
- Scripts idempotentes.
- Todo recurso debe tener `deploy`, `validate` y, cuando aplique, `destroy`.
- Las pruebas deben referenciar explícitamente el componente de arquitectura validado.
