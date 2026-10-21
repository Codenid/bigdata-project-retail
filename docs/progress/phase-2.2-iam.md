# Fase 2.2 — IAM

- **Objetivo:** crear y validar exclusivamente las identidades del Streaming Core.
- **Componentes implementados:** RS-SEC-001 (`rs-dev-str-sa-dataflow`) y RS-SEC-002
  (`rs-dev-sec-sa-deployer`). Bootstrap recibió TokenCreator solo sobre RS-SEC-002;
  RS-SEC-002 recibió Service Account Viewer sobre ambas cuentas. RS-SEC-001 no
  recibió roles runtime. No se crearon claves ni roles personalizados.
- **Archivos creados/modificados:** `infra/config/iam.json`, `infra/iam/manage.py`,
  `infra/iam/README.md`, `infra/tests/test_phase22.py`, `infra/bootstrap/apis.py`
  y `docs/standards/resource-catalog.md`.
- **Comandos principales:**

  ```bash
  gcloud iam roles describe roles/iam.serviceAccountViewer --format=json
  python3 -m infra.iam.manage --mode deploy
  python3 -m infra.iam.manage --mode validate
  python3 -m infra.iam.manage --mode deploy
  python3 -m unittest discover -s infra/tests -v
  ```

- **Resultado de validación:** ambas cuentas existen y permiten get/getIamPolicy
  mediante impersonación del deployer. Validate terminó con código 0. La
  reejecución final de deploy terminó con `applied_changes=0`, `changes=0` y código 0.
  No se detectaron roles amplios directos revisados; no se certifican privilegios
  heredados de organización, carpeta o grupos.
- **Pruebas:** 16 pruebas locales correctas en conjunto para 2.1/2.2; cubren
  idempotencia, permisos insuficientes, rechazo de roles amplios y validación sin
  mutaciones.
- **Incidencias relevantes:** se corrigió el flag --project al consultar roles
  predefinidos globales. getAccessToken fue denegado tras crear el binding; después
  de propagación IAM y reintentos funcionó sin ampliar permisos.
- **Estado final:** COMPLETADO y aprobado. Sin APIs adicionales ni recursos de
  datos o cómputo. Evidencia retrospectiva de ejecuciones del 2026-10-21. El futuro
  lanzador Dataflow podría requerir Service Account User sobre RS-SEC-001; sigue
  diferido. Destroy integrado corresponde a una fase posterior.
