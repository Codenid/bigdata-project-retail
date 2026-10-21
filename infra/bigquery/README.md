# FASE 2.5 — Gold Insights Retail

Gestiona únicamente RS-DATA-003, dataset rs_dev_gold vacío en la location regional
configurada (us-central1). Nombres y labels se resuelven desde config/dev.env y
Resource Catalog. Infra/config/bigquery.json contiene IAM y metadata aprobados.
No se añaden variables de expiración o billing al env.

## Propiedades y costo

Sin defaultTableExpirationMs ni defaultPartitionExpirationMs: Gold es persistente.
El insert omite ambas propiedades y no envía storageBillingModel. Validate acepta
null/ausencia de expiraciones y reporta el billing model observado, sin modificarlo.
Cifrado Google-managed, clasificación internal y labels serving/gold/multi.
La clasificación es metadata y no sustituye controles de acceso.

No crea tablas, views, materialized views, modelos, rutinas, schemas de negocio,
reservations, slots, BI Engine, cargas ni jobs. Las lecturas de tablas/modelos/
rutinas verifican exclusivamente que el dataset esté vacío; no leen filas ni
inician cómputo. Un dataset vacío sin jobs ni capacidad reservada no tiene costo
esperado de almacenamiento de datos o procesamiento de consultas.

Las futuras consultas se plantean on-demand. Este script no configura ni
certifica asignaciones de reservations heredadas; deberán revisarse antes de
consultar. No habilita APIs adicionales ni Reservation API. No hay un campo
on-demand por dataset; no confundirlo con el modelo de facturación de almacenamiento.

## Ejecución

```bash
python3 -m infra.bigquery.manage --mode deploy
python3 -m infra.bigquery.manage --mode validate
python3 -m infra.bigquery.manage --mode deploy
python3 -m unittest discover -s infra/tests -v
```

Requiere bootstrap autenticado y fases anteriores completas. Python usa JSON APIs
oficiales y gcloud para autenticación e IAM; no ejecuta SQL ni bq jobs. Los tokens
viven en memoria y no se imprimen. Proyecto/región solo se aplican a la sesión.
Errores 403 no se interpretan como ausencia; solo un 404 de get significa ausente.
Los reintentos 403 posteriores a grants son acotados y visibles, sin ampliar roles.

Deploy crea el dataset atómicamente con metadata de catálogo y access explícito
para projectOwners (administradores existentes). No introduce projectReaders,
projectWriters o acceso público. La representación ACL OWNER equivale a BigQuery
Data Owner del dataset; no es una asignación de roles/owner al proyecto.

Si el dataset existe, se valida proyecto, nombre, pertenencia y location antes
de modificar. Los parches de metadata o ACL usan If-Match/etag, preservando entradas
ajenas. CMEK u opciones de dataset externo fuera de alcance provocan error. El
dataset debe seguir vacío; no se adopta uno ajeno ni se reemplaza location.

## IAM temporal y seguridad administrativa

- roles/bigquery.user solo a nivel proyecto al necesitar creación. Incluye jobs,
  capacidad más amplia que mínimo estricto que el script no utiliza.
- roles/bigquery.dataOwner solo sobre rs_dev_gold durante operaciones necesarias.
- RS-SEC-001 no recibe permisos runtime. No se otorgan BigQuery Admin ni roles
  básicos Owner/Editor, ni se crean nuevas identidades o claves.

El bootstrap conserva sus permisos existentes. Antes de cualquier grant, se
comprueba con projects.testIamPermissions que dispone de get/getIamPolicy,
update/setIamPolicy y delete a nivel proyecto, independientemente del deployer.
También debe poder aplicar/retirar el binding temporal de proyecto, como en fases
anteriores; el script no le concede esos permisos.

Se captura la ACL inicial. Tras crear se detecta un posible Owner automático del
creador; si no existe, bootstrap concede Data Owner temporal solo al dataset.
El acceso del creador puede aparecer como OWNER o rol completo, userByEmail o
principal IAM; las comparaciones normalizan estas representaciones.

Finalmente, con token bootstrap independiente del deployer, se leen permisos y
ACL actuales ANTES de retirar cualquier Owner creado. La retirada requiere prueba
administrativa y etag actual. Se confirma mediante lectura posterior. Si no puede
probar administración suficiente, se conserva ese acceso y se reporta fallo de
cleanup: no se arriesga un dataset sin administrador. La limpieza del rol temporal
de proyecto se intenta incluso si la del dataset falla. No se modifican accesos
preexistentes, incluidos grants condicionales u otros miembros.

Un fallo de cleanup no se oculta. SIGKILL/caída del host puede impedir finally;
revisar la política y evidencia antes de reintentar. No ejecutar operaciones
concurrentes sobre el dataset o bindings temporales. Las comprobaciones de acceso
no certifican todas las relaciones heredadas de grupos/organización; la prueba
administrativa debe pasar con el bootstrap configurado y su lectura real.

`changes` cuenta cambios persistentes del dataset; `project_iam_changes` y
`dataset_iam_changes` cuentan por separado grants/retiros temporales. Reejecutar
debe dejar changes=0 y restaurar los accesos iniciales. Si existía un permiso,
se conserva y se reporta como preexistente.

## Destroy/recreate

```bash
# Preview: sin eliminar dataset; puede gestionar ACL temporal:
python3 -m infra.bigquery.manage --mode destroy
# Elimina solo rs_dev_gold si está vacío:
python3 -m infra.bigquery.manage --mode destroy --execute-destroy
# Recreación:
python3 -m infra.bigquery.manage --mode deploy
```

No hay --purge ni deleteContents=true. Se rechazan tablas/views, modelos y rutinas
antes de eliminar y se usa deleteContents=false como protección adicional. Un
dataset ausente se tolera. No elimina proyectos, cuentas, APIs o recursos de otras
fases. Destroy/recreate destructivo debe distinguirse de pruebas simuladas.

Si Free Trial, cuotas o políticas impiden una operación, se informa el error sin
habilitar servicios, ampliar permisos ni sustituir la arquitectura.

Referencias:
- https://docs.cloud.google.com/bigquery/docs/reference/rest/v2/datasets
- https://docs.cloud.google.com/bigquery/docs/datasets
- https://docs.cloud.google.com/resource-manager/reference/rest/v1/projects/testIamPermissions
- https://docs.cloud.google.com/bigquery/docs/managing-datasets
