# Fase 2.6 — Deploy integrado Streaming Core

- **Objetivo:** orquestar la infraestructura existente sin recursos GCP nuevos.
- **Componentes implementados:** Configuration → Bootstrap/APIs → IAM Foundation
  → Pub/Sub → Storage → BigQuery. Entradas Bash mínimas y coordinación Python
  reutilizan módulos actuales. Fallo parcial detiene dependencias con [SKIP],
  preserva recursos válidos y limpia IAM temporal; sin rollback destructivo.
  Pub/Sub comparte con Storage el ciclo de binding temporal: conserva accesos
  preexistentes y retira solo los creados por la operación. changes e iam_changes
  se reportan por separado. Gold mantiene su ACL temporal y administración bootstrap.
- **Archivos creados/modificados:** tres wrappers en scripts/,
  infra/streaming_core/manage.py, infra/iam/temporary.py, módulos bootstrap, IAM,
  Pub/Sub y Storage, infra/config/pubsub.json, infra/pubsub/README.md,
  pruebas 2.2/2.3/2.4/2.6, README.md, catálogo, plan y esta evidencia.
- **Comandos principales:**

  ```bash
  ./scripts/deploy_streaming_core.sh
  ./scripts/validate_streaming_core.sh
  ./scripts/deploy_streaming_core.sh
  ./scripts/destroy_streaming_core.sh  # Preview protegido, sin borrar recursos
  python3 -m unittest discover -s infra/tests -v
  ```

  La eliminación explícita requiere --execute-destroy. Completa todos los
  prechecks antes de borrar Gold → buckets → subscription → tópicos. Rechaza
  artefactos BigQuery, objetos Storage y subscriptions adicionales, incluidas las
  de otros proyectos. No ofrece purge/force, eliminación recursiva ni teardown de
  identidades. Conserva IAM Foundation, APIs, proyecto y billing.
- **Resultado de validación:** primer deploy integrado real con código 0,
  changes=0 e iam_changes=4. Configuration, Bootstrap/APIs, IAM Foundation,
  Pub/Sub, Storage y BigQuery terminaron correctamente. Storage añadió/retiró
  su binding temporal (2); Gold añadió/retiró Data Owner del dataset (2), sin
  BigQuery User de proyecto. Pub/Sub detectó binding preexistente y lo preservó
  (iam_changes=0, preexisting_binding=true). La validación independiente terminó con código 0, changes=0 e iam_changes=4,
  con los mismos ciclos temporales y cleanup confirmado. El segundo deploy terminó con código 0, changes=0 e iam_changes=4;
  idempotencia confirmada, sin cambios permanentes. Los nueve componentes del
  catálogo quedaron válidos. Preview integrado terminó con código 0, changes=0 e iam_changes=4:
  Gold y buckets vacíos, sin subscriptions adicionales; todos los planes con
  execute=false. Sin destroy real ni eliminación de identidades/foundation.
- **Pruebas:** 80 pruebas locales correctas, reejecutadas tras el segundo deploy. Cubren orden, configuración externa,
  fail-fast, conteos parciales ante errores, preview, prechecks previos a toda
  eliminación, idempotencia y limpieza/preservación IAM. Bash válido y wrapper
  ejecutable desde otra carpeta. Destroy/recreate real permanece simulado.
- **Incidencias relevantes:** permanece el roles/pubsub.editor preexistente del
  deployer; no se retiró porque la regla aprobada protege bindings anteriores a
  la operación. El nuevo código no crea bindings persistentes. La migración de
  ese acceso previo requiere resolver explícitamente esta excepción.
  Latencia en llamadas GCP, sin cambios de credenciales
  ni configuración global. Los bindings preexistentes se preservan incluso si
  proceden de versiones anteriores; no se infiere ownership por nombre. No
  ejecutar operaciones concurrentes sobre los mismos recursos/bindings. SIGTERM
  permite finally; SIGKILL/caída del host puede impedirlo. Un fallo de cleanup es
  error visible. Los conteos de un módulo fallido pueden estar incompletos y el
  resumen lo señala. Bronze conserva soft delete y posible costo residual de
  siete días. No hay cómputo, consultas, cargas ni APIs adicionales.
- **Estado final:** COMPLETADO y validado en GCP el 2026-10-21, con el binding
  Pub/Sub preexistente conservado y reportado. Sin recursos nuevos ni avance a
  fases posteriores.
