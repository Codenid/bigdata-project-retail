# Fase 3.1 — Event Contracts

- **Objetivo:** implementar contratos de hechos de origen conforme al diseño
  aprobado de la Arquitectura de Solución, conservando los seis nombres oficiales.
- **Componentes implementados:** siete JSON Schemas Draft 2020-12 (envelope y seis
  eventos), referencias locales sin red, validación estructural/calendario UTC y
  coherencia semántica cantidad/capacidad. expected_delivery_timestamp obligatorio
  conserva el compromiso del origen. Siete ejemplos válidos y siete inválidos,
  ficticios, sin PII real. Sin scenario, vertical, KPI ni resultados calculados.
  IoT: V1 P/V3 S; telemetría y sensores de almacén: V1 P/V4 P.
- **Archivos creados/modificados:** contracts/streaming/*.schema.json,
  contracts/streaming/validation.py, contracts/streaming/examples/{valid,invalid}/,
  contracts/tests/test_streaming_contracts.py, requirements-dev.txt, README.md,
  docs/data/streaming-contracts.md, docs/data/source-to-vertical-matrix.md,
  docs/architecture/{architecture-overview,implementation-mapping}.md,
  docs/standards/{resource-naming,resource-catalog}.md,
  docs/plan/implementation-plan.md y esta evidencia.
- **Comandos principales:**

  ```bash
  python3 -m pip install -r requirements-dev.txt
  python3 -m unittest discover -s contracts/tests -v
  python3 -m unittest discover -s infra/tests -v
  git status --short --branch
  ```

- **Resultado de validación:** los siete schemas son válidos, los siete ejemplos
  positivos pasan y los siete negativos se rechazan. Stock mayor que capacidad
  pasa la estructura estándar pero falla validate_event por incoherencia del
  hecho. No hay thresholds de negocio. Se admiten anomalías observadas, lecturas
  negativas de temperatura y compromisos vencidos sin convertirlos en resultados.
- **Pruebas:** 21 de contratos y 80 existentes de infraestructura: 101 correctas.
  Cubren campos requeridos/condicionales, opcionales omitidos, enums, unidades,
  fuentes/versiones oficiales, null, propiedades extra, formatos/calendario UTC,
  fronteras numéricas, JSON no finito, referencias sin red y regla semántica.
- **Incidencias relevantes:** no se necesitó instalar dependencias en este
  entorno; jsonschema 4.25.1 y referencing 0.37.0 ya estaban disponibles y quedan
  declaradas. Se usa comprobación explícita del calendario, sin depender de
  extras opcionales de formatos. Perfil UTC con Z, segundos 00–59. No se validan
  unicidad global, consistencia entre eventos o ausencia efectiva de PII mediante
  schema; requieren controles posteriores. No se ejecutaron operaciones GCP.
  Se registró primero la decisión arquitectónica y después documentación/contratos.
- **Estado final:** COMPLETADO localmente. Sin productores CLI, generación masiva,
  publicación, procesamiento, tablas ni avance a FASE 3.2. Infraestructura intacta.
