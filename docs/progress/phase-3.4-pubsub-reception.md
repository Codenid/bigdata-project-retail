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
- **Estado del cierre inicial:** herramienta implementada y probada; inspección real ejecutada
  con resultado **UNAVAILABLE (0/46)**. Recepción histórica completa no demostrada.
  Una prueba fresca requiere aprobación separada. ACK real sigue sin autorización.
  Sin Dataflow, procesamiento downstream ni avance a otra fase.


## Prueba fresca de cierre funcional — 2026-10-22 UTC

- **Objetivo:** seis eventos unitarios nuevos, uno por tipo oficial, desde
  RS-STR-001 hasta pull/validación en RS-STR-002, y ACK condicionado a comprobar
  previamente los seis eventos. La autorización no modifica contratos ni IAM.
- **Contexto:** test_id local `phase34-fresh-2026-10-22T055905-562383Z`.
  Inicio: `2026-10-22T05:59:05.562386Z`.
  UUID generados por el productor unitario existente, vinculados a este test_id
  exclusivamente mediante el registro local; sin campos o atributos nuevos.
  OPERATOR_ACCOUNT y acceso consume verificados antes de publicar y antes de
  cada inspección. No se registran correos ni credenciales.
- **Ejecución:** orquestación puntual temporal fuera del repositorio, reutilizando
  el CLI unitario, Client.pull(10), inspect y el hash canónico existentes.
  El CLI de recepción conserva su protección histórica --ack/--verify-phase33;
  no se modificó ni se sustituyó el manifiesto Fase 3.3 por estos eventos nuevos.
  Los handles ACK permanecieron solo en memoria y nunca se guardaron.

  Comandos del productor ejecutados exactamente una vez por tipo:

  ```bash
  python -m producers.streaming.send_event --type clic_event
  python -m producers.streaming.send_event --type iot_event
  python -m producers.streaming.send_event --type stock_event
  python -m producers.streaming.send_event --type location_event
  python -m producers.streaming.send_event --type telemetry_event
  python -m producers.streaming.send_event --type warehouse_sensor_event
  ```

  Estos comandos son evidencia histórica; no deben repetirse para continuar
  esta prueba, porque generarían publicaciones adicionales.

| event_type | event_id publicado | message_id confirmado | event_timestamp UTC | schema_version | Recepción única |
|---|---|---|---|---|---|
| clic_event | 6c199cfd-2ff1-4ec3-be68-b976abdf6374 | 22067327073790487 | 2026-10-22T05:59:38.049830Z | 1.0 | VALID / NOT_ACKED |
| iot_event | 77dd29c1-2fd2-4561-a3b6-28f5f8b782e8 | 22066855567524564 | 2026-10-22T06:00:07.632416Z | 1.0 | VALID / NOT_ACKED |
| stock_event | f5ebc82f-a8c6-4b6f-97fd-7ee90d42739c | 23178254826964668 | 2026-10-22T06:00:37.816868Z | 1.0 | VALID / NOT_ACKED |
| location_event | e1418141-5689-4cfb-8606-edd9258326dc | 22072742644624631 | 2026-10-22T06:01:11.391741Z | 1.0 | NO RECUPERADO |
| telemetry_event | eb565729-71cb-4ffd-9a4d-556f9933419b | 23178068550409253 | 2026-10-22T06:01:55.761881Z | 1.0 | VALID / NOT_ACKED |
| warehouse_sensor_event | 3cdf148f-6592-4bee-947f-9ebac6328ef9 | 23178500500208427 | 2026-10-22T06:02:38.021794Z | 1.0 | NO RECUPERADO |

  Hashes esperados SHA-256 del JSON canónico de cada evento publicado:

| event_type | SHA-256 |
|---|---|
| clic_event | f3dd7f383bebfe199116d823df33959f9c69132de48ee361245867237cfc61a9 |
| iot_event | 005721c2c11bcb77c8b5b71a3f9b6425c392af095ab49fb385b772bbaeae7fdf |
| stock_event | 653d396270d394b095eece257381991781c35c1bc3f88fbb7e71ce71185bf211 |
| location_event | 6e945ffae54e76779aa109479b2185ed02a0aee3da4de2a98dc6fea8c3075e8a |
| telemetry_event | d0d89a7aca58c7461c1b4237f59001ba9dc28ee44ee980f066b5a8f7c504979b |
| warehouse_sensor_event | 703d62667376a11105070022f80a0d3a487e918860ec7c96643038ad6a9eb593 |

- **Recepción y correspondencia:** inspección inicial sin ACK inmediatamente
  después de completar las seis publicaciones; un pull con maxMessages=10
  devolvió un mensaje válido. Se detuvo VERIFY_SIX por faltar cinco esperados.
  Una segunda invocación manual independiente, también un pull con máximo 10,
  devolvió cuatro mensajes válidos. Telemetry apareció en ambas inspecciones.
  Ninguna invocación implementó loops, polling o reintentos automáticos.

| Inspección | UTC de validación | Entregas | Válidos | Inválidos | ACK |
|---|---|---:|---:|---:|---:|
| 1 | 2026-10-22T06:03:19.460984Z | 1 | 1 | 0 | 0 |
| 2 | 2026-10-22T06:05:53.173880Z | 4 | 4 | 0 | 0 |

  Resultado acumulado: **6 publicados; 5 entregas; 4 eventos únicos válidos;
  2 esperados no recuperados; 1 redelivery entre inspecciones; 0 conflictos;
  0 ajenos; ACKED=0**. Todos los mensajes observados coinciden con event_id,
  message_id, event_type, event_timestamp, schema_version y hash del publicado,
  sin exigir orden. Los faltantes son location_event y warehouse_sensor_event.
  La primera recepción comprobó telemetry_event; la segunda comprobó clic_event,
  telemetry_event, stock_event e iot_event. No se envió ninguna operación ACK.
- **Incidencias y límite de autorización:** las seis publicaciones y los dos
  pulls fueron aceptados por Pub/Sub; las dos comprobaciones auxiliares
  terminaron en VERIFY_SIX porque sus lotes individuales estaban incompletos.
  No hubo errores de transporte ni publicaciones inciertas. Una tercera
  inspección fue solicitada, pero la revisión automática rechazó su ejecución:
  consideró que excedía el pull único autorizado y que el ACK por subconjuntos
  podía contradecir la condición de comprobar el lote completo. No se ejecutó
  esa tercera inspección ni se intentó una vía alternativa tras el rechazo.
  La cantidad parcial no demuestra pérdida de eventos ni expiración.
- **Pruebas y seguridad:** 195 pruebas del repositorio correctas (40 consumidores,
  54 productores, 21 contratos, 80 infraestructura). Se ejecutaron además seis
  comprobaciones locales temporales del guard de la prueba fresca: seis exactos
  desordenados, faltantes, conflicto de ID, esperado inválido, ajeno y duplicado
  idéntico. Las seis pasaron; no forman parte de la suite versionada.
  Revisión de secretos sin hallazgos; config/dev.env ignorado, ejemplo versionado.
- **Archivos modificados en esta validación:** esta evidencia, README.md y
  docs/architecture/implementation-mapping.md. Sin cambios en código versionado,
  manifiesto histórico, infraestructura, IAM, retención o ack deadline.
- **Estado final de la prueba fresca:** **PARTIAL (4/6 únicos válidos), ACKED=0**.
  El cierre funcional solicitado todavía no está demostrado. Se requiere
  autorización explícita para inspecciones adicionales de los seis mensajes
  existentes y su confirmación protegida tras comprobar el conjunto completo.
  No se deben republicar estos eventos. No se avanzó a Dataflow u otra fase.
