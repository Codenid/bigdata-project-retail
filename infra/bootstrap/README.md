# FASE 2.1 — Configuración y bootstrap/APIs

Implementado: configuración central, contraste de nombres y labels con el catálogo
aprobado, preflight de proyecto/facturación y habilitación idempotente de APIs.
No crea cuentas, bindings IAM, tópicos, buckets, datasets ni jobs. El bootstrap
inicial usa una identidad existente; la creación del deployer corresponde a 2.2.

Requisitos: Python 3.10+, gcloud y una identidad autenticada. No se requiere bq
hasta implementar BigQuery. No se cambia la configuración global de gcloud:
cada comando recibe explícitamente proyecto y cuenta. Proyecto y región se
configuran para los subprocesos de esta sesión mediante CLOUDSDK_CORE_PROJECT y
CLOUDSDK_COMPUTE_REGION; no se persiste una configuración global.
Antes de consultar el proyecto se exige que BOOTSTRAP_ACCOUNT coincida con la
cuenta activa de gcloud. Las llamadas autenticadas posteriores validan el acceso
real; listar una cuenta por sí solo no garantiza que el token sea válido.
Se acepta PROJECT_ID como alias de GCP_PROJECT_ID; si ambos existen deben coincidir.

```bash
cp config/dev.env.example config/dev.env
# Completar proyecto, región, location, suffix y BOOTSTRAP_ACCOUNT.
python3 -m infra.bootstrap.apis --mode config
python3 -m infra.bootstrap.apis --mode plan
python3 -m infra.bootstrap.apis --mode deploy
python3 -m infra.bootstrap.apis --mode validate
python3 -m unittest discover -s infra/tests -v
```

`config` y `plan` son locales y no invocan GCP. `deploy` consulta el proyecto y
facturación, lista APIs y habilita únicamente las faltantes. `validate` hace las
mismas comprobaciones sin mutaciones y falla si falta alguna API. Se espera
`OK: bootstrap/APIs válido` con código 0. Los errores y stderr de gcloud se
muestran; no se convierten en recursos ausentes. Una habilitación parcial puede
reintentarse: la siguiente ejecución calcula nuevamente las APIs faltantes.

La cuenta inicial necesita consultar proyecto y facturación, listar servicios y
habilitarlos (Service Usage Admin o permisos equivalentes). Debe tener acceso a
un proyecto existente con Service Usage utilizable; no se crea proyecto ni se
vincula facturación. No se conceden permisos automáticamente en esta fase.

APIs en `infra/config/apis.json`, conforme al plan aprobado. Incluyen servicios
para el runtime futuro; habilitarlos no lanza pipelines. No se deshabilitarán en
destroy. Las identidades administradas por Google son dependencias del servicio.

La ubicación es regional y común en este corte. Los nombres provienen del
catálogo Markdown, evitando duplicar un inventario de recursos. Las variables de
entorno prevalecen sobre las claves presentes en el archivo env. El archivo se
interpreta como KEY=VALUE literal: no admite comandos, expansión shell ni comillas.
La fase 2.3 mantiene la residencia Pub/Sub bajo política por defecto, sin variables
de residencia. Ack, retención y expiración están externalizados; bootstrap no
aplica estas propiedades a recursos.

Los tests usan un proyecto ficticio y un runner simulado: verifican rechazo de
nombres ajenos, validación de configuración, idempotencia y ausencia de mutaciones
al validar o fallar facturación. No acreditan permisos ni conectividad reales.

Referencias oficiales:
- https://docs.cloud.google.com/sdk/gcloud/reference/services/enable
- https://docs.cloud.google.com/sdk/gcloud/reference/billing/projects/describe

## Evidencia de validación — 2026-10-21

FASE 2.1 validada contra GCP: cuenta activa coincidente, proyecto ACTIVE y
facturación habilitada. Se corrigió GCP_LOCATION de US a us-central1 con aprobación
del usuario, conservando el scope regional del catálogo.

Se habilitaron cloudresourcemanager, compute, dataflow, iam, iamcredentials y
pubsub (dominio googleapis.com). BigQuery, Logging, Monitoring, Service Usage y
Storage ya estaban habilitados. Validate finalizó con missing_apis=[] y código 0;
repetir deploy también devolvió missing_apis=[] y código 0, sin habilitaciones.
Las nueve pruebas locales pasaron. No se crearon recursos de aplicación ni IAM.
Los estados del catálogo permanecen approved: las APIs habilitadas no implican
que los nueve recursos estén desplegados.

El sandbox inicialmente impidió abrir credentials.db de gcloud. La ejecución
fuera del sandbox autorizada permitió usar la autenticación existente; no fue
necesario copiar credenciales ni conceder permisos IAM adicionales.
