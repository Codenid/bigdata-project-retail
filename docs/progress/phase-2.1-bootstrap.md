# Fase 2.1 — Bootstrap/APIs

- **Objetivo:** validar configuración y habilitar las APIs del Streaming Core.
- **Componentes implementados:** configuración externa contrastada con catálogo,
  cuenta activa, acceso a proyecto, facturación y APIs; proyecto/región en sesión.
- **Archivos creados/modificados:** `config/dev.env.example`, configuración local
  ignorada `config/dev.env`, `infra/config/settings.py`, `infra/config/apis.json`,
  `infra/bootstrap/apis.py`, `infra/bootstrap/README.md`,
  `infra/tests/test_phase21.py` y `.gitignore`.
- **Comandos principales:**

  ```bash
  python3 -m infra.bootstrap.apis --mode config
  python3 -m infra.bootstrap.apis --mode deploy
  python3 -m infra.bootstrap.apis --mode validate
  python3 -m unittest discover -s infra/tests -v
  ```

- **Resultado de validación:** en GCP, proyecto ACTIVE y facturación habilitada.
  Se habilitaron cloudresourcemanager, compute, dataflow, iam, iamcredentials y
  pubsub (`.googleapis.com`); BigQuery, Storage, Logging, Monitoring y Service
  Usage ya estaban habilitados. Validate devolvió `missing_apis=[]`, código 0;
  repetir deploy también terminó con código 0 sin habilitaciones adicionales.
- **Pruebas:** nueve pruebas locales correctas al cierre de 2.1; incluyen
  configuración, cuenta activa, sesión e idempotencia con runner simulado.
- **Incidencias relevantes:** GCP_LOCATION se corrigió de US a us-central1 con
  aprobación del usuario. El acceso al directorio de credenciales fue bloqueado
  por el sandbox y resuelto mediante ejecución autorizada fuera del sandbox.
- **Estado final:** COMPLETADO y aprobado. No se crearon recursos de aplicación,
  identidades, claves ni cómputo en esta fase. Evidencia retrospectiva de las
  ejecuciones del 2026-10-21; no representa una nueva consulta a GCP.
