# Fase 2.3 — Pub/Sub Streaming Core

- **Objetivo:** aprovisionar exclusivamente dos tópicos y una subscription pull
  catalogados, sin procesamiento ni productores.
- **Componentes implementados:** RS-STR-001 `rs-dev-str-ps-events`, RS-STR-002
  `rs-dev-str-ps-events-dataflow` asociada a RS-STR-001, RS-STR-003
  `rs-dev-str-ps-insights` sin subscription. Labels de catálogo, scope global y
  location n/a. Ack 60 s, retención 3600 s, retain acked false, expiración 604800 s,
  retry inmediato; ordering, exactly-once, DLQ, filtros, push y export desactivados.
  Sin schemas ni Message Storage Policy explícita ni variables de residencia.
  RS-SEC-002 recibió temporalmente roles/pubsub.editor a nivel proyecto: más
  amplio que mínimo estricto, debe revisarse posteriormente. RS-SEC-001 conserva
  su ausencia de permisos runtime.
- **Archivos creados/modificados:** `infra/config/pubsub.json`,
  `infra/pubsub/manage.py`, `infra/pubsub/README.md`, `infra/tests/test_phase23.py`,
  `infra/config/settings.py`, `config/dev.env.example`, configuración local
  ignorada, `infra/bootstrap/README.md`, `docs/standards/resource-catalog.md`,
  `docs/architecture/implementation-mapping.md`, `README.md` y esta evidencia.
- **Comandos principales:**

  ```bash
  python3 -m infra.pubsub.manage --mode deploy
  python3 -m infra.pubsub.manage --mode validate
  python3 -m infra.pubsub.manage --mode deploy
  python3 -m infra.pubsub.manage --mode destroy  # Solo previsualización
  python3 -m unittest discover -s infra/tests -v
  ```

  Para eliminar y recrear explícitamente (destructivo, pierde backlog):

  ```bash
  python3 -m infra.pubsub.manage --mode destroy --execute-destroy
  python3 -m infra.pubsub.manage --mode deploy
  ```

- **Resultado de validación:** primer deploy real con código 0 y changes=4
  (un binding y tres recursos). Validate real con código 0 y changes=0.
  La segunda ejecución real de deploy terminó con código 0 y changes=0. Destroy
  en previsualización terminó con código 0, execute=false y los tres recursos
  esperados; no eliminó recursos ni bindings.
- **Pruebas:** 30 pruebas locales correctas (2.1/2.2/2.3). La suite cubre deploy/validate/redeploy, destroy/recreate,
  idempotencia, drift, permisos insuficientes, pertenencia, features excluidas,
  preservación de Message Storage Policy por defecto y subscriptions adicionales
  incluso desde otros proyectos. Los tests usan runner simulado; destroy/recreate
  destructivo no se ejecutó contra GCP.
- **Incidencias relevantes:** ninguna falla de deploy o validate real registrada.
  Gcloud muestra advertencias informativas por impersonación. Costo esperado
  prácticamente nulo sin tráfico, sin cómputo o retención de tópico. El tráfico
  futuro puede generar cargos; retención corta no es un límite monetario.
- **Estado final:** COMPLETADO, validado en GCP el 2026-10-21. No se avanzó a
  Storage ni se crearon recursos adicionales. Catálogo conserva estados de
  aprobación; esta evidencia registra el resultado del despliegue.
