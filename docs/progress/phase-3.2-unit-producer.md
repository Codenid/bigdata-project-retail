# Fase 3.2 — Productor CLI unitario

- **Objetivo:** construir, validar y publicar un hecho sintético por ejecución
  en RS-STR-001, según el diseño aprobado de la Arquitectura de Solución.
- **Componentes implementados:** seis fábricas sin dependencia runtime de ejemplos;
  source/schema_version obtenidos de los schemas; validate_event reutilizado.
  La cadena serializada tras validar se entrega sin alteraciones al adaptador
  gcloud independiente. OPERATOR_ACCOUNT separado de BOOTSTRAP_ACCOUNT, cuenta
  activa comprobada sin --account y selección explícita al publicar. Sin fallback,
  overrides de identidad, modificación de IAM, infraestructura o consumo.
  Dry-run termina localmente mostrando evento/destino, sin gcloud ni red.
- **Archivos creados/modificados:** producers/streaming/{build_event,publish,
  send_event}.py, producers/streaming/README.md,
  producers/tests/test_unit_producer.py, config/dev.env.example, README.md,
  requirements-dev.txt (comentario), docs/architecture/{architecture-overview,
  implementation-mapping}.md, docs/standards/resource-catalog.md,
  docs/plan/implementation-plan.md y esta evidencia. config/dev.env recibió
  OPERATOR_ACCOUNT explícito con el mismo correo inicial del bootstrap, sin
  cambiar autenticación: archivo local ignorado, no incluido en el commit.
- **Comandos principales:**

  ```bash
  python -m producers.streaming.send_event --type stock_event --dry-run
  python -m producers.streaming.send_event --type stock_event
  python -m unittest discover -s producers/tests -v
  python -m unittest discover -s contracts/tests -v
  python -m unittest discover -s infra/tests -v
  git status --short --branch
  ```

  Los seis tipos se ejercitaron primero con --dry-run. Después se ejecutó una
  publicación por cada tipo oficial (sin --dry-run), sin count, rate o escenarios.
- **Resultado de validación:** seis dry-runs correctos, cada evento validado,
  published=false y message_id=null. Luego seis publicaciones confirmadas, una
  por tipo, con event_id y message_id distintos. Todos los eventos aceptados
  volvieron a comprobarse localmente contra el validador. Destino único verificado:
  `projects/retailsmart-bigdata/topics/rs-dev-str-ps-events`.

  | event_type | event_id | message_id | timestamp UTC local del resultado | resultado |
  |---|---|---|---|---|
  | clic_event | 8fad3c9b-4627-4e46-8263-cdef4aac6800 | 23177663042349380 | 2026-10-22T03:34:44.580000Z | OK |
  | iot_event | 1ae807f9-ee81-46f1-80da-f75a6c882888 | 22067123768726962 | 2026-10-22T03:35:09.479451Z | OK |
  | stock_event | 8e5a8ca8-71cc-4b99-b4a0-ef46a5123f32 | 22066887242441111 | 2026-10-22T03:35:39.061170Z | OK |
  | location_event | f9b6a459-f83e-44db-b48c-6bfe0b9f76a8 | 23177966070177721 | 2026-10-22T03:36:03.274483Z | OK |
  | telemetry_event | 6192e2c0-5426-408d-8653-2d7f9673a552 | 22070468390501839 | 2026-10-22T03:36:27.451954Z | OK |
  | warehouse_sensor_event | 3ed05f17-c596-4472-b75b-6a6d58311bfc | 22068824244394242 | 2026-10-22T03:36:51.238016Z | OK |

  timestamp corresponde a la confirmación observada por el CLI, no publishTime
  del servidor. Los ACK no certifican procesamiento downstream. No se consultaron
  ni consumieron subscriptions para comprobar el resultado.
- **Pruebas:** 24 nuevas del productor + 21 de contratos + 80 de infraestructura:
  125 correctas. Cobertura de fábricas/identidades nuevas, entidades coherentes,
  metadata de schema sin fixtures, configuración externa, dry-run sin GCP,
  validación antes de autenticar/publicar, serialización exacta, cuenta activa
  distinta/missing, overrides de identidad, permiso denegado, timeout, falta de
  message_id, error de red, stderr visible y rechazo de flags fuera de alcance.
- **Incidencias relevantes:** el primer intento real se detuvo en OPERATOR por
  sintaxis incorrecta de consulta SDK (gcloud config list auth). No llegó a
  invocar publish: cero mensajes enviados. Se corrigió a auth/, se ajustó la
  prueba y se repitieron todas las suites y los seis dry-runs antes de ejecutar
  las seis publicaciones. No se reintentó ninguna publicación incierta. No se
  necesitaron grants IAM, nuevas APIs, login ni cambios de configuración SDK.
  El CLI no reintenta desde la aplicación; un fallo de transporte puede dejar
  resultado incierto. Cada invocación nueva crea otro hecho, no un replay.
  Costo esperado bajo para seis mensajes pequeños, sin garantía de gratuidad;
  retención existente de una hora, sin consumidor ni cómputo. Sin cambios a
  contratos ni módulos de infraestructura.
- **Estado final:** COMPLETADO. Seis publicaciones reales confirmadas; sin
  consumo, generación masiva, Dataflow, procesamiento ni avance a FASE 3.3.
