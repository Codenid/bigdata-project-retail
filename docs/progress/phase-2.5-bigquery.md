# Fase 2.5 — BigQuery / Gold Insights Retail

- **Objetivo:** aprovisionar únicamente el dataset persistente RS-DATA-003 vacío,
  sin tablas, cargas, queries, jobs ni capacidad dedicada.
- **Componentes implementados:** dataset `rs_dev_gold` en us-central1, scope
  regional y cifrado Google-managed. Labels project=retailsmart, environment=dev,
  domain=data, managed_by=script, component_id=rs-data-003,
  data_classification=internal, role=serving, layer=gold, vertical=multi.
  Sin default table/partition expiration ni storageBillingModel explícito.
  Access inicial explícito conserva administradores existentes projectOwners;
  OWNER en esa ACL es Data Owner de dataset, no roles/owner del proyecto.
- **Archivos creados/modificados:** `infra/config/bigquery.json`,
  `infra/bigquery/manage.py`, `infra/bigquery/README.md`,
  `infra/tests/test_phase25.py`, `docs/standards/resource-catalog.md`, `README.md`
  y esta evidencia. El env y sus ejemplos no requieren variables adicionales.
- **Comandos principales:**

  ```bash
  python3 -m infra.bigquery.manage --mode deploy
  python3 -m infra.bigquery.manage --mode validate
  python3 -m infra.bigquery.manage --mode deploy
  python3 -m unittest discover -s infra/tests -v
  # Preview: sin eliminar dataset, con eventual ACL temporal:
  python3 -m infra.bigquery.manage --mode destroy
  # Eliminación explícita solo si está vacío:
  python3 -m infra.bigquery.manage --mode destroy --execute-destroy
  ```

- **Resultado de validación:** primer deploy real terminó con código 0, changes=1,
  project_iam_changes=2 y dataset_iam_changes=2. Confirmó ambas expiraciones null,
  location y labels; storageBillingModel observado ausente, nunca configurado.
  No hubo Owner automático en esta creación. Se añadió/retiró Data Owner temporal
  solo del dataset y BigQuery User temporal del proyecto; ambos retiros quedaron
  confirmados. La administración efectiva del bootstrap se probó antes de crear
  y antes de retirar Owner, con permisos del proyecto y lectura real del dataset.
  Validate independiente y segundo deploy terminaron con código 0 y changes=0.
  En ambos project_iam_changes=0 y dataset_iam_changes=2: no fue necesario
  reotorgar BigQuery User; Data Owner temporal quedó retirado y confirmado.
- **Pruebas:** 62 pruebas locales correctas para 2.1–2.5 antes del deploy y
  reejecutadas tras el segundo deploy. Cubren
  idempotencia, ausencia de configuración de expiraciones/billing en insert,
  limpieza de Owner automático o temporal, preservación de accesos existentes y
  condicionales, normalización de principales, fallo de bootstrap/cleanup,
  errores de permisos, conflictos de nombre/location/pertenencia y rechazo de
  artefactos. Destroy/recreate está simulado; no se eliminó el dataset real.
- **Incidencias relevantes:** sin errores registrados en el primer deploy.
  `changes` cuenta cambios persistentes del dataset; métricas IAM separan accesos
  temporales. Si no se demuestra administración bootstrap, cleanup conserva el
  acceso del dataset y reporta error antes de arriesgar bloqueo; aun así intenta
  limpiar el rol de proyecto. No se eliminan accesos preexistentes. SIGKILL/caída
  del host puede impedir finally: revisar políticas antes de reintentar.
  Dataset vacío sin jobs ni reservas tiene costo esperado prácticamente nulo.
  Futuras consultas se plantean on-demand; no se verifican asignaciones heredadas
  de reservations en esta fase ni se habilita Reservation API.
- **Estado final:** COMPLETADO y validado en GCP el 2026-10-21. Sin permisos BigQuery runtime
  para RS-SEC-001, APIs adicionales, tablas, views, cargas, cómputo ni cambios en
  otros componentes. No se avanzó a 2.6.
