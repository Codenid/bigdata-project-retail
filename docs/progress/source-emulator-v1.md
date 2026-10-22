# Source Emulator V1 — Streaming

- **Objetivo:** emular las seis aplicaciones/dispositivos fuente mediante UI
  local Python/Streamlit y engine desacoplado, publicación real sobre RS-STR-001,
  reutilizando contratos/fábricas/perfiles aprobados de la Arquitectura de Solución.
- **Componentes:** Overview/Streaming/Batch/Activity; seis fuentes con
  START/STOP/SEND ONCE, START ALL/STOP ALL, presets y rate custom hasta 20 evt/s;
  escenarios finitos compatibles, métricas y últimos 50 eventos/JSON. Batch solo
  Coming next. Lease de sesión, ventana máxima, cierre explícito y atexit.
  Transporte REST operativo en memoria, sin retries, atributos o cambios IAM.
  CLI unitario/escenarios conserva publicación gcloud por defecto.
- **Archivos:** apps/{source_emulator.py,requirements.txt,README.md},
  .streamlit/config.toml, producers/emulator/{sources.py,engine.py,transport.py,
  __init__.py,tests/test_engine.py,tests/test_ui.py},
  scripts/demo_source_emulator.py, producers/streaming/publish.py (hook opcional),
  config/dev.env.example y Markdown de arquitectura, plan, mapping, README/evidencia.
  Sin cambios en schemas, contratos, perfiles, infraestructura o Resource Catalog.
- **Decisión:** registrada antes de implementar en architecture-overview.md y
  implementation-plan.md. Esta solicitud adelanta el corte local de PASO 5;
  no autoriza Dataflow ni Batch. Reloj sintético de perfiles conservado; rate
  controla emisión sin reescribir hechos. MAX_RATE/ventana/lease externalizados.
- **Comandos principales:**

  ```bash
  python -m pip install -r apps/requirements.txt
  streamlit run apps/source_emulator.py
  python -m unittest discover -s producers/emulator/tests -v
  python -m unittest discover -s consumers/tests -v
  python -m unittest discover -s producers/tests -v
  python -m unittest discover -s contracts/tests -v
  python -m unittest discover -s infra/tests -v
  # Demo histórica ya ejecutada; volver a ejecutarla publicaría nuevos eventos:
  python scripts/demo_source_emulator.py --publish --report /tmp/retailsmart-source-emulator-v1-real-demo.json
  git status --short --branch
  ```

- **Validación local:** Streamlit 1.51.0 iniciado en http://127.0.0.1:8501,
  /_stcore/health devolvió HTTP 200/ok. AppTest comprueba apertura sin acceso GCP,
  fuentes visibles, conexión simulada, SEND ONCE, Activity/JSON, Batch Coming next,
  incompatibilidad de escenarios y desconexión. La demo real se ejecutó con el
  mismo engine que usa la UI; no se presenta como automatización de navegador.
- **Demo real:** 2026-10-22T16:45:14.215935+00:00 → 2026-10-22T16:45:50.523414+00:00.
  Destino `projects/retailsmart-bigdata/topics/rs-dev-str-ps-events`. Identidad activa OPERATOR_ACCOUNT comprobada, sin
  registrar correo ni token. No se cambiaron IAM, APIs, recursos o contratos.

| Fuente | Rate objetivo | Ejecución | Publicados confirmados | Errores | Estado |
|---|---:|---|---:|---:|---|
| Estantería Inteligente | 1 evt/s | 5 segundos | 5 | 0 | STOPPED |
| Tracking Logístico / Repartidores | 1 evt/s | 5 segundos | 5 | 0 | STOPPED |
| Cámaras Frigoríficas | 1 evt/s | TELEMETRY_ANOMALY finito | 4 | 0 | STOPPED |
| **Total** | — | — | **14** | **0** | **0 workers activos** |

  Evolución térmica confirmada: **4.5 → 4.6 → 9 → 12 °C**.
  No se consumieron mensajes ni se enviaron ACK de subscriptions.

| event_type | event_id | message_id | event_timestamp UTC | Resultado |
|---|---|---|---|---|
| stock_event | 7d42c780-f93e-4780-9390-c7707b136a8c | 22067210696163636 | 2026-10-22T16:45:35.525163Z | OK |
| stock_event | 3a3e80ad-e4d3-4047-bd60-cca9b207027b | 23179383808758367 | 2026-10-22T16:45:36.507365Z | OK |
| stock_event | 47b80539-363a-42e2-aa05-e8800a67135c | 23178911160927509 | 2026-10-22T16:45:37.507382Z | OK |
| stock_event | 258971a1-9bee-4ae0-bca3-5d30744b21ec | 23179749998533441 | 2026-10-22T16:45:38.507415Z | OK |
| stock_event | 5bde1bd9-33bc-45c5-9fda-3c32f41d09ff | 23177932055273340 | 2026-10-22T16:45:39.507413Z | OK |
| location_event | 5b6ef9af-cbc7-49d8-a454-42455dfa98a7 | 23179791072923210 | 2026-10-22T16:45:40.511840Z | OK |
| location_event | 1a3279d5-3e7e-4ca8-b194-a24994814d1d | 23178257601942736 | 2026-10-22T16:45:41.511893Z | OK |
| location_event | 0f1bdd68-40ce-4b96-b4a8-2616e538be61 | 22074105410877830 | 2026-10-22T16:45:42.511838Z | OK |
| location_event | 65076a8a-d932-471c-b7e5-e9ed8621956c | 20329440238393285 | 2026-10-22T16:45:43.511931Z | OK |
| location_event | 21161505-5503-45ff-99b9-b28ee2ed6683 | 22070468406084789 | 2026-10-22T16:45:44.511935Z | OK |
| telemetry_event | bf4df0c2-efa2-5ad5-b480-1d42d5b429fe | 23179521726553942 | 2026-10-22T16:45:45.517725Z | OK |
| telemetry_event | 94bd9b93-03e8-5fc9-ac6b-b48f0307d4dc | 20330023372767297 | 2026-10-22T16:46:45.517725Z | OK |
| telemetry_event | 5f6ebcc6-8bea-5405-8b48-6d34fd8367af | 22067180779932366 | 2026-10-22T16:47:45.517725Z | OK |
| telemetry_event | c30aa137-d345-51e1-a3d4-cfd612957f34 | 23179308791550579 | 2026-10-22T16:48:45.517725Z | OK |

- **Pruebas:** 39 nuevas (32 engine/transporte, 7 UI) y 195 existentes: **234**
  correctas. Cubren start/stop, aislamiento, rate/reinicio, send_once, start_all,
  validación previa, fallos sin retry, métricas, límite de historial, escenarios
  y correlaciones, repetición con IDs nuevos, cierre/lease y envío en curso.
  Transporte simulado comprueba destino, identidad, expiración, respuesta y
  ausencia de atributos; CLI anteriores mantienen sus pruebas intactas.
- **Incidencias:** AppTest inicial seleccionó un botón por posición ambigua;
  se añadieron claves explícitas y guardas de conexión, y se corrigió el test.
  La comprobación diagnóstica de sockets no tenía permiso netlink en sandbox;
  el arranque real y health HTTP verificaron el servicio sin cambiar permisos.
  La demo GCP no presentó errores. El lease detecta cierre del navegador con
  retraso acotado; STOP espera el envío en curso y no puede revocar una petición
  ya aceptada. Rate es máximo/objetivo y no garantiza throughput ante latencia.
- **Seguridad/costo:** bind loopback, sin tokens/credenciales/ackId en UI o
  evidencia, token solo en memoria. Ventana máxima 300s, lease máximo 10s,
  MAX_RATE máximo 20 por fuente, sin cola de catch-up ni retries propios.
  No hay cómputo GCP nuevo; costo limitado a bytes publicados. STOP/desconectar
  detiene nuevas emisiones. Revisión de secretos y env ignorado/verificado.
- **Estado final:** V1 implementada, probada y ejecutada; demo real **14/14**
  con message_id distintos, 0 errores y 0 workers activos al cerrar el engine.
  Aplicación local iniciada, sin productores autoactivos. Sin Batch, Dataflow,
  consumo de mensajes o asignaciones IAM. La cobertura histórica de recepción
  Fase 3.4 sigue PARTIAL, sin inferir procesamiento downstream por esta demo.
