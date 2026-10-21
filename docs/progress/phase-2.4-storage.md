# Fase 2.4 — Storage Streaming Core

- **Objetivo:** aprovisionar únicamente los tres buckets regionales aprobados con
  protección de originales, reconstrucción de curados y limpieza técnica.
- **Componentes implementados:** RS-DATA-001 `rs-dev-data-gcs-bronze-rsg`,
  RS-DATA-002 `rs-dev-data-gcs-silver-rsg`, RS-STR-004
  `rs-dev-str-gcs-dataflow-rsg`. Todos en us-central1, STANDARD, acceso uniforme,
  Public Access Prevention enforced y cifrado Google-managed. Sin CMEK,
  versioning, Bucket Lock ni retention policy. Bronze: soft delete 604800 s y
  sin lifecycle. Silver: soft delete 0 y sin lifecycle. Técnico: soft delete 0
  y exactamente una regla Delete con age=1. Labels derivados del catálogo.
- **Archivos creados/modificados:** `infra/config/storage.json`,
  `infra/storage/manage.py`, `infra/storage/README.md`,
  `infra/tests/test_phase24.py`, `config/dev.env.example`, configuración local
  ignorada `config/dev.env`, `docs/standards/resource-catalog.md`, `README.md`
  y esta evidencia. El loader central existente sigue resolviendo nombres y
  labels; Storage valida sus propiedades específicas con el manifiesto externo.
- **Comandos principales:**

  ```bash
  python3 -m infra.storage.manage --mode deploy
  python3 -m infra.storage.manage --mode validate
  python3 -m infra.storage.manage --mode deploy
  python3 -m unittest discover -s infra/tests -v
  # Previsualización; IAM temporal, sin eliminar buckets/objetos:
  python3 -m infra.storage.manage --mode destroy
  # Solo cuando se apruebe una eliminación real:
  python3 -m infra.storage.manage --mode destroy --execute-destroy
  # Para buckets con datos, añadir --purge explícitamente.
  ```

- **Resultado de validación:** primer deploy real terminó con código 0 y
  changes=3. Creó/retiró el binding temporal Storage Admin del deployer, confirmado
  en política del proyecto: iam_changes=2, temporary_binding_removed=true,
  preexisting_binding=false. Las propiedades efectivas de los tres buckets
  coincidieron con el diseño. Validate independiente terminó con código 0 y
  changes=0. Segundo deploy terminó con código 0 y changes=0. En las tres
  operaciones iam_changes=2 y temporary_binding_removed=true; no quedó el
  binding temporal creado por las operaciones. No hubo bindings Storage Admin
  preexistentes para el deployer en estas ejecuciones.
- **Pruebas:** 45 pruebas locales correctas para 2.1–2.4, ejecutadas antes del
  deploy y nuevamente después del segundo deploy.
  Cubren propiedades diferenciadas, idempotencia, drift, guardia de metageneración,
  conflicto de proyecto/location/pertenencia, retención bloqueada, bindings
  públicos/runtime, validación sin escrituras, limpieza IAM ante errores,
  conservación de grants preexistentes y destroy/recreate con purga explícita.
  Destroy/recreate está simulado; no se eliminan datos reales en esta fase.
- **Incidencias relevantes:** sin errores registrados en el primer deploy. Se
  usa la JSON API oficial para creación atómica con labels y protecciones;
  gcloud gestiona autenticación e IAM. Tokens solo en memoria. `changes` cuenta
  modificaciones de buckets y `iam_changes` registra grant/revoke por separado.
  La limpieza temporal restaura el binding inicial; no elimina grants previos.
  Un fallo de cleanup se reporta y una terminación forzada puede impedir finally.
  Soft delete de Bronze conserva recuperación y puede mantener costo siete días
  tras eliminar datos. Lifecycle técnico es asíncrono; no garantiza borrado exacto
  a las 24 horas. No hay límite monetario por bucket.
- **Estado final:** COMPLETADO y validado en GCP el 2026-10-21. Sin APIs adicionales,
  permisos runtime para RS-SEC-001, objetos de prueba ni recursos de cómputo.
  No se avanzó a 2.5.
