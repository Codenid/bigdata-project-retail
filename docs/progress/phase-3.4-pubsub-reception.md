# Fase 3.4 — Validación de recepción Pub/Sub

- **Objetivo:** inspeccionar eventos de RS-STR-002 y validar contratos y evidencia
  histórica, con ACK explícito restringido al manifiesto de Fase 3.3.
- **Componentes implementados:** CLI de pull puntual, adaptador REST sin retries
  propios, guard operativo reutilizado, comprobación informativa de consume,
  decodificación estricta Base64/UTF-8/JSON y validate_event existente, verificador
  de IDs/hash, conteos únicos y consolidación offline. Un pull por invocación;
  --limit 1–50, predeterminado 10; --ack exige --verify-phase33. Solo confirma
  eventos válidos idénticos al manifiesto; ajenos e inválidos quedan sin ACK.
- **Archivos creados/modificados:** consumers/__init__.py,
  consumers/streaming/{__init__.py,pull_events.py,pubsub.py,verify_phase33.py,README.md},
  consumers/tests/test_pull_events.py,
  consumers/tests/fixtures/phase33-expected.json, README.md,
  docs/architecture/implementation-mapping.md y esta evidencia.
  Sin cambios de contratos, fábricas, perfiles, infraestructura o IAM.
- **Comandos principales:**

  ```bash
  python -m unittest discover -s consumers/tests -v
  python -m unittest discover -s producers/tests -v
  python -m unittest discover -s contracts/tests -v
  python -m unittest discover -s infra/tests -v
  python -m consumers.streaming.pull_events --limit 46 --verify-phase33
  # Consolidación offline de reportes guardados, sin llamadas a GCP:
  python -m consumers.streaming.verify_phase33 reporte.json
  git status --short --branch
  ```

  La inspección real se ejecutó una sola vez, después de pasar pruebas locales.
  El comando de consolidación es una referencia de uso; no realiza pull ni ACK.
- **Resultado de validación real:** reporte finalizado 2026-10-22T05:50:38.516226Z.
  Destino: `projects/retailsmart-bigdata/subscriptions/rs-dev-str-ps-events-dataflow`.
  Configuración existente config/dev.env; OPERATOR_ACCOUNT activo verificado,
  sin registrar su correo. testIamPermissions confirmó consume antes del pull;
  la llamada pull también terminó satisfactoriamente (código de salida 0).
  No se requieren permisos nuevos. Un único pull, maxMessages=46, sin --ack.

  | Métrica | Resultado |
  |---|---:|
  | Mensajes recuperados | 0 |
  | Eventos válidos | 0 |
  | Eventos inválidos | 0 |
  | Esperados encontrados únicos | 0 |
  | Esperados faltantes | 46 |
  | Duplicados | 0 |
  | Conflictos | 0 |
  | Mensajes ajenos | 0 |
  | ACK enviados | 0 |
  | Estado histórico | **UNAVAILABLE** |

  | Tipo | Esperados históricos | Encontrados |
  |---|---:|---:|
  | clic_event | 9 | 0 |
  | iot_event | 6 | 0 |
  | stock_event | 9 | 0 |
  | location_event | 7 | 0 |
  | telemetry_event | 7 | 0 |
  | warehouse_sensor_event | 8 | 0 |
  | **TOTAL** | **46** | **0** |

  Los 46 event_id faltantes corresponden a la totalidad del manifiesto
  [phase33-expected.json](../../consumers/tests/fixtures/phase33-expected.json),
  derivado de los ACK/contextos versionados en commit
  039f3b218b2f25681e969b69b46a9cc4dba84729. Hash SHA-256 de JSON canónico,
  reconstruido offline; el consumidor no depende de fábricas en runtime.
  No hay registros por mensaje porque el pull devolvió un lote vacío.
- **Pruebas:** 40 nuevas y 155 existentes: **195 correctas** (consumidores 40,
  productores 54, contratos 21, infraestructura 80). Cubren límite/destino fijo,
  identidad, permisos, un único pull, ausencia de ACK predeterminado, rechazo de
  --ack aislado, ACK simulado exclusivo de esperados, mensajes ajenos/invalidos,
  coincidencia de hashes, conflictos tardíos, duplicados, orden distinto,
  COMPLETE/PARTIAL/UNAVAILABLE, timeout sin reintento, saneamiento de reportes
  y consolidación offline. No se ejecutó ACK real.
- **Incidencias relevantes:** ninguna llamada real falló. UNAVAILABLE no indica
  automáticamente fallo del consumidor. Retención aprobada de 3600 segundos:
  los mensajes históricos podrían haber expirado, pero un pull vacío no prueba
  expiración ni ausencia de backlog. No se repitió el pull ni se generaron
  eventos para forzar la aceptación. Sin secretos en la evidencia; env local
  ignorado y ejemplo versionado. Sin nuevas APIs, recursos, roles o dependencias.
- **Estado final:** herramienta implementada y probada; inspección real ejecutada
  con resultado **UNAVAILABLE (0/46)**. Recepción histórica completa no demostrada.
  Una prueba fresca requiere aprobación separada. ACK real sigue sin autorización.
  Sin Dataflow, procesamiento downstream ni avance a otra fase.
