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
- **Estado final:** COMPLETADO en validación local. Publicación real de los
  escenarios PENDIENTE DE APROBACIÓN. Sin Producer Console, Dataflow ni
  procesamiento downstream.
