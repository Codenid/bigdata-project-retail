# Fase 3.3 — Escenarios sintéticos controlados

- **Objetivo:** construir seis perfiles pequeños, coherentes y reproducibles
  conforme al diseño aprobado de la Arquitectura de Solución, sin publicar.
- **Componentes implementados:** scenarios.json, composición/validación completa
  en scenarios.py y CLI run_scenario.py, dry-run predeterminado. Contexto opcional
  de fábricas con run_id/start_time, UUID determinísticos por contenido/posición
  y entidades compartidas. Schemas y validate_event reutilizados sin cambios.
  NORMAL es baseline transversal de operación; DELIVERY_DELAY solo V1/V3.
  Sin seed, count, aleatoriedad, rate, retries propios ni ordering garantizado.
- **Archivos creados/modificados:** producers/streaming/{scenarios.json,
  scenarios.py,run_scenario.py,build_event.py,README.md},
  producers/tests/test_scenarios.py, README.md, docs/data/synthetic-scenarios.md,
  docs/architecture/{architecture-overview,implementation-mapping}.md y esta
  evidencia. send_event.py, publish.py, contratos e infraestructura sin cambios.
- **Comandos principales:**

  ```bash
  python -m producers.streaming.run_scenario --scenario NORMAL --dry-run
  python -m producers.streaming.run_scenario --scenario HIGH_DEMAND --dry-run
  python -m producers.streaming.run_scenario --scenario LOW_STOCK --dry-run
  python -m producers.streaming.run_scenario --scenario DELIVERY_DELAY --dry-run
  python -m producers.streaming.run_scenario --scenario TELEMETRY_ANOMALY --dry-run
  python -m producers.streaming.run_scenario --scenario WAREHOUSE_EQUIPMENT_DEGRADATION --dry-run
  python -m unittest discover -s producers/tests -v
  python -m unittest discover -s contracts/tests -v
  python -m unittest discover -s infra/tests -v
  git status --short --branch
  ```

  Aceptación reproducible: --run-id acceptance-3.3-001 y
  --start-time 2026-10-21T12:00:00Z. Se repitieron los seis perfiles con el mismo
  contexto y con run_id acceptance-3.3-002, siempre en dry-run y sin GCP.
- **Resultado de validación:** seis perfiles y 46 eventos en el conjunto canónico.
  Todos pasan validate_event y coherencia de secuencia. Reportes con
  confirmed_count=0 y message_id=null. Misma salida completa en repetición del
  contexto; identificadores distintos para otro run_id. Ningún evento contiene
  nombres de escenarios ni metadata de planificación. Evidencia SHA-256 por
  perfil sobre eventos JSON canónicos UTF-8 unidos por LF, sin LF final:

  | Perfil | Eventos | SHA-256 | Publicaciones reales |
  |---|---:|---|---:|
  | NORMAL | 18 | 52eb24ee4915ef25fde808ae71bc3654a6c9a919e70fb713077643b3c82ab2c7 | 0 |
  | HIGH_DEMAND | 12 | 1a9c020315773b1707fcafb7924b3a6c33614d84b9cd63a48078de52817d2cf8 | 0 |
  | LOW_STOCK | 3 | 876ae709cdb8cebf301c2a150c4090c0c1565b13b4c89add807f3924f71b1b9c | 0 |
  | DELIVERY_DELAY | 4 | c2f75eda92177ef7c563c893f3d06bf29bd8701550ae4089324a4122d91e8045 | 0 |
  | TELEMETRY_ANOMALY | 4 | 10e44a5f841b69c986688dc6567175fdb707d1702c34f0c9d1e924e4e84111b4 | 0 |
  | WAREHOUSE_EQUIPMENT_DEGRADATION | 5 | ee5d7a9d65382e3f6f5d9456d8d28c7d455a70be1971a2bdfabba35834185ea8 | 0 |

- **Pruebas:** 30 nuevas de escenarios y las 125 existentes: 155 correctas
  (54 de productores, 21 de contratos y 80 de infraestructura). Confirman:
  mismo scenario/run_id/start_time → mismas cadenas; distinto run_id → nueva
  ejecución lógica; ausencia de nombres de escenarios en eventos; plan inválido
  bloquea toda publicación; CLI unitario 3.2 compatible sin modificarlo.
  También cubren valores/cantidades exactas, correlaciones, cronología, compromiso
  inmutable, prevalidación de último evento, strings inmutables ante mutación
  posterior, dry-run sin red/reloj/UUID aleatorio, envío simulado en orden, fallo
  parcial sin retries y ausencia de atributos Pub/Sub añadidos. No se ejecutaron
  publicaciones reales: los casos --publish están completamente simulados.
- **Incidencias relevantes:** primer dry-run local detectó que la comprobación
  de correlación exigía el customer_id opcional ausente; se corrigió para
  comprobar identificadores presentes y delegar obligatoriedad al schema.
  Una expectativa de prueba usaba orden alfabético de schemas para empates;
  se corrigió para comprobar el orden local aprobado del perfil. Ambos casos
  resueltos antes de aceptación. Sin librerías, IAM, APIs o recursos nuevos.
  Dry-run no genera costo GCP. El mecanismo de publicación requiere contexto
  explícito y OPERATOR_ACCOUNT; un ACK futuro no certifica procesamiento ni
  exactamente una vez. No se consumen mensajes ni se hace rollback/reenvío.
- **Estado final local:** COMPLETADO. La publicación real se autorizó y ejecutó
  posteriormente; su evidencia se registra a continuación.


## Validación real controlada — 2026-10-22 UTC

- **Objetivo:** publicar una sola ejecución de cada perfil aprobado, 46 mensajes
  en total, sin consumirlos ni modificar contratos, perfiles, fábricas,
  infraestructura o IAM.
- **Contexto:** commit de implementación
  `58b9bcc5be96dad9df5ae422172ef6df3008475a`; perfil versión `1.0`.
  Destino único RS-STR-001:
  `projects/retailsmart-bigdata/topics/rs-dev-str-ps-events`.
  Configuración cargada desde `config/dev.env` ignorado por Git; presencia de
  OPERATOR_ACCOUNT y coincidencia con la cuenta activa verificadas por
  `check_operator`, sin overrides de credenciales o impersonación.
  Existencia del tópico confirmada mediante `gcloud pubsub topics describe`.
  No se registran correos operativos ni credenciales.
- **Prevalidación:** planes completos de los seis perfiles construidos y
  validados antes de iniciar publicaciones. Run IDs nuevos, distintos de los
  usados en dry-run. Los 46 eventos publicados coinciden con esos planes;
  46 event_id y 46 message_id distintos. No se añadieron atributos Pub/Sub.
  El escenario existe exclusivamente en el reporte local.
- **Archivos modificados en este cierre:** README.md y esta evidencia.

| Escenario local | run_id | start_time UTC explícito | Esperados | Confirmados | Fallidos | Pendientes | Inciertos |
|---|---|---|---:|---:|---:|---:|---:|
| NORMAL | real-normal-001 | 2026-10-22T04:32:37Z | 18 | 18 | 0 | 0 | 0 |
| HIGH_DEMAND | real-high-demand-001 | 2026-10-22T04:32:38Z | 12 | 12 | 0 | 0 | 0 |
| LOW_STOCK | real-low-stock-001 | 2026-10-22T04:32:39Z | 3 | 3 | 0 | 0 | 0 |
| DELIVERY_DELAY | real-delivery-delay-001 | 2026-10-22T04:32:40Z | 4 | 4 | 0 | 0 | 0 |
| TELEMETRY_ANOMALY | real-telemetry-anomaly-001 | 2026-10-22T04:32:41Z | 4 | 4 | 0 | 0 | 0 |
| WAREHOUSE_EQUIPMENT_DEGRADATION | real-warehouse-degradation-001 | 2026-10-22T04:32:42Z | 5 | 5 | 0 | 0 | 0 |
| **TOTAL** | — | — | **46** | **46** | **0** | **0** | **0** |

**Comandos ejecutados:** cada escenario se ejecutó individualmente y el
resultado se revisó antes de iniciar el siguiente. Estos comandos son evidencia
histórica; volver a ejecutarlos publicaría mensajes adicionales.

```bash
python -m producers.streaming.run_scenario --scenario NORMAL --run-id real-normal-001 --start-time 2026-10-22T04:32:37Z --publish
python -m producers.streaming.run_scenario --scenario HIGH_DEMAND --run-id real-high-demand-001 --start-time 2026-10-22T04:32:38Z --publish
python -m producers.streaming.run_scenario --scenario LOW_STOCK --run-id real-low-stock-001 --start-time 2026-10-22T04:32:39Z --publish
python -m producers.streaming.run_scenario --scenario DELIVERY_DELAY --run-id real-delivery-delay-001 --start-time 2026-10-22T04:32:40Z --publish
python -m producers.streaming.run_scenario --scenario TELEMETRY_ANOMALY --run-id real-telemetry-anomaly-001 --start-time 2026-10-22T04:32:41Z --publish
python -m producers.streaming.run_scenario --scenario WAREHOUSE_EQUIPMENT_DEGRADATION --run-id real-warehouse-degradation-001 --start-time 2026-10-22T04:32:42Z --publish
```

**Registro por mensaje:** event_timestamp representa el instante sintético
observado, no la hora de recepción del ACK. Todos los registros siguientes
pertenecen al tópico RS-STR-001 indicado arriba.

| Escenario local | event_type | event_id | event_timestamp UTC | message_id | Resultado |
|---|---|---|---|---|---|
| NORMAL | clic_event | 93adc15b-2849-51cc-879f-4cc91dbf5024 | 2026-10-22T04:32:37.000000Z | 23177917877751178 | OK |
| NORMAL | iot_event | 21d90f01-19c8-558c-a3ad-f812567b5f5d | 2026-10-22T04:32:37.000000Z | 22075977170835365 | OK |
| NORMAL | stock_event | 1b3cfb89-f7e6-5f9e-b609-e3bcc6626321 | 2026-10-22T04:32:37.000000Z | 23178569644142629 | OK |
| NORMAL | location_event | 73d50027-57f5-5272-aea2-44342dcc745f | 2026-10-22T04:32:37.000000Z | 22072371936776913 | OK |
| NORMAL | telemetry_event | 964de132-8e82-5f24-8670-ee20f5e99162 | 2026-10-22T04:32:37.000000Z | 23178410487282054 | OK |
| NORMAL | warehouse_sensor_event | 068433c2-5892-536e-9ee4-ff14fb96e954 | 2026-10-22T04:32:37.000000Z | 20329233854659752 | OK |
| NORMAL | clic_event | f29b65bc-c16b-568e-8f81-7d0322a58154 | 2026-10-22T04:33:37.000000Z | 23178569644167604 | OK |
| NORMAL | iot_event | f1c9a473-b022-5125-95e1-e3a9f76e2144 | 2026-10-22T04:33:37.000000Z | 22067188218664806 | OK |
| NORMAL | stock_event | b77f845d-c4f5-5f04-8fdc-34d0afe85c4a | 2026-10-22T04:33:37.000000Z | 22066959007034376 | OK |
| NORMAL | location_event | af4017d9-ff09-54e6-905a-fd3533447c91 | 2026-10-22T04:33:37.000000Z | 22074734268396545 | OK |
| NORMAL | telemetry_event | cd627345-a348-5ee1-83f6-b7dde764ae57 | 2026-10-22T04:33:37.000000Z | 23179490024827698 | OK |
| NORMAL | warehouse_sensor_event | fd3617fb-9706-5fd4-85b2-1a9e5ad6ca5f | 2026-10-22T04:33:37.000000Z | 23176990032500969 | OK |
| NORMAL | clic_event | 9fd3f36e-6926-5678-af9d-3729400c8ff2 | 2026-10-22T04:34:37.000000Z | 23177770606905994 | OK |
| NORMAL | iot_event | db0e361d-f2c4-5ffe-9bde-9cd5d9d3324f | 2026-10-22T04:34:37.000000Z | 22067185213891998 | OK |
| NORMAL | stock_event | 8fc55a71-cc02-5292-a8c6-dcec695d9973 | 2026-10-22T04:34:37.000000Z | 23178571792050369 | OK |
| NORMAL | location_event | ce3433e4-ab1a-5174-86c9-81b4be729766 | 2026-10-22T04:34:37.000000Z | 22067437075682299 | OK |
| NORMAL | telemetry_event | 180c921d-f320-5c29-8f0a-4e8029cd78df | 2026-10-22T04:34:37.000000Z | 22071876599164388 | OK |
| NORMAL | warehouse_sensor_event | 30c25c41-94bb-5561-bd8a-4cb6f4cd24c7 | 2026-10-22T04:34:37.000000Z | 23177921890850036 | OK |
| HIGH_DEMAND | clic_event | d22ff30d-bb33-5f94-b6d9-6425ddb0756d | 2026-10-22T04:32:38.000000Z | 23177948818572328 | OK |
| HIGH_DEMAND | iot_event | b2effee3-11e0-5816-bbb9-a0a69f1f4f02 | 2026-10-22T04:32:38.000000Z | 23177691518983678 | OK |
| HIGH_DEMAND | stock_event | 61edead6-ca46-5193-a0a5-fe43f3f63f9c | 2026-10-22T04:32:38.000000Z | 23177625654323657 | OK |
| HIGH_DEMAND | clic_event | 848e943f-afed-58f3-939d-e817ef4eb513 | 2026-10-22T04:32:48.000000Z | 23178159543260608 | OK |
| HIGH_DEMAND | clic_event | f7189333-b605-5358-b4e9-01509af1207a | 2026-10-22T04:32:58.000000Z | 23178333694420925 | OK |
| HIGH_DEMAND | clic_event | a2e7ede5-b4d6-5385-843f-3568b453d6c9 | 2026-10-22T04:33:08.000000Z | 22066918461513734 | OK |
| HIGH_DEMAND | clic_event | 5a5824a1-5c52-583a-8ded-ae2b55d8cca2 | 2026-10-22T04:33:18.000000Z | 23177772128928016 | OK |
| HIGH_DEMAND | clic_event | 1c624ca8-5884-5895-85bf-22784b9983a9 | 2026-10-22T04:33:28.000000Z | 22066855566456176 | OK |
| HIGH_DEMAND | iot_event | b5901f9f-12b4-5368-a707-d439b4eb272e | 2026-10-22T04:33:38.000000Z | 23178163550792870 | OK |
| HIGH_DEMAND | stock_event | 06557723-2fc4-542d-9123-ca906230f936 | 2026-10-22T04:33:38.000000Z | 23177949859817156 | OK |
| HIGH_DEMAND | iot_event | 6d750c8a-8f6b-532d-b85a-ccefcfc11836 | 2026-10-22T04:34:38.000000Z | 22069104174853440 | OK |
| HIGH_DEMAND | stock_event | b4621b11-5386-51fa-96b2-2572345b4f77 | 2026-10-22T04:34:38.000000Z | 23177800802797867 | OK |
| LOW_STOCK | stock_event | 9f11eb17-208d-52de-8ae0-7f8a784cc159 | 2026-10-22T04:32:39.000000Z | 23177724060164399 | OK |
| LOW_STOCK | stock_event | ffa58a1f-2610-5b19-879e-afa3f04fb7bb | 2026-10-22T04:33:39.000000Z | 23178062350798864 | OK |
| LOW_STOCK | stock_event | 4f25fb92-0fd7-5ce9-9c64-8dad44cda922 | 2026-10-22T04:34:39.000000Z | 22069320723382986 | OK |
| DELIVERY_DELAY | location_event | ee5e0353-376c-508c-b857-57d2fc9e81df | 2026-10-22T04:32:40.000000Z | 22067265098873646 | OK |
| DELIVERY_DELAY | location_event | 92283ce5-c964-58af-bf20-5e9fb17216e8 | 2026-10-22T04:33:40.000000Z | 22071306365918700 | OK |
| DELIVERY_DELAY | location_event | 4e7cca9d-eff4-58e8-8fba-b46a7465609b | 2026-10-22T04:35:40.000000Z | 22071306365920777 | OK |
| DELIVERY_DELAY | location_event | 5c72962d-7a6e-58a6-92a3-0d41065bcc68 | 2026-10-22T04:36:40.000000Z | 23178456772030932 | OK |
| TELEMETRY_ANOMALY | telemetry_event | 50ca8dd1-77ab-57f5-99c1-f08d243ab216 | 2026-10-22T04:32:41.000000Z | 23179490024906737 | OK |
| TELEMETRY_ANOMALY | telemetry_event | c75be0a3-4265-5f83-91b2-8b90b92e10cb | 2026-10-22T04:33:41.000000Z | 22074734268469028 | OK |
| TELEMETRY_ANOMALY | telemetry_event | 54c4bba2-bba7-5500-9a77-e2e05ae1b927 | 2026-10-22T04:34:41.000000Z | 22067169920635780 | OK |
| TELEMETRY_ANOMALY | telemetry_event | b8b2acdc-d19d-5d76-8d51-d676895c01c1 | 2026-10-22T04:35:41.000000Z | 22069117820705862 | OK |
| WAREHOUSE_EQUIPMENT_DEGRADATION | warehouse_sensor_event | c997249e-caf3-55d2-a71d-774cf99cd2f7 | 2026-10-22T04:32:42.000000Z | 23177787085347697 | OK |
| WAREHOUSE_EQUIPMENT_DEGRADATION | warehouse_sensor_event | e38b006f-a6bc-58a6-bb0b-3f4296f553da | 2026-10-22T04:33:42.000000Z | 22075525359398748 | OK |
| WAREHOUSE_EQUIPMENT_DEGRADATION | warehouse_sensor_event | 6d224767-36ff-55bb-93de-c0ca530df553 | 2026-10-22T04:34:42.000000Z | 22074492151547872 | OK |
| WAREHOUSE_EQUIPMENT_DEGRADATION | warehouse_sensor_event | 0932a85f-9acf-5e1e-be98-c6c892dec7fa | 2026-10-22T04:35:42.000000Z | 23178162495281551 | OK |
| WAREHOUSE_EQUIPMENT_DEGRADATION | warehouse_sensor_event | 247585c9-b038-5b9e-9129-f5b14a5b31c3 | 2026-10-22T04:36:42.000000Z | 22067108301070461 | OK |

- **Pruebas posteriores:** `python -m unittest discover -s producers/tests -v`
  (54), `python -m unittest discover -s contracts/tests -v` (21) y
  `python -m unittest discover -s infra/tests -v` (80): **155 correctas**.
- **Incidencias:** ninguna publicación falló; no hubo reintentos ni reenvíos.
  Una comprobación auxiliar textual de start_time falló por normalización
  `.000000Z`; la comparación de instantes UTC confirmó los seis contextos.
  No se modificó código ni se repitieron publicaciones por esta comprobación.
- **Seguridad:** revisión de los cambios sin secretos; config/dev.env sigue
  ignorado y config/dev.env.example sigue versionado. Evidencia limitada a
  identificadores sintéticos, IDs de Pub/Sub y contexto operativo no secreto.
- **Estado final:** COMPLETADO, **46/46 publicaciones aceptadas por Pub/Sub**,
  cero fallidos, pendientes o inciertos. Los message_id confirman publicación;
  no demuestran recepción ni procesamiento downstream. No se consumieron
  mensajes. Sin cambios de IAM o infraestructura y sin avance a Fase 3.4.
