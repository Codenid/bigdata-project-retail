# RetailSmart — Resource Catalog

## 1. Objetivo

Catálogo maestro de recursos de infraestructura RetailSmart.

La arquitectura es la fuente de verdad.

> Ningún script debe crear un recurso que no esté previamente definido en este catálogo.

Estado inicial: **Streaming Core v1**

---

## 2. Catálogo Streaming

| Component ID | Componente de Arquitectura | Dominio | Vertical | Servicio GCP | Tipo | Entorno | Nombre físico | Scope | Location | Role | Layer | Clasificación | Owner | Managed by | Estado |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| RS-STR-001 | Tópico Eventos Retail | Streaming | V1/V4 | Pub/Sub | Topic | dev | rs-dev-str-ps-events | global | n/a | ingest | n/a | internal | RetailSmart | script | approved |
| RS-STR-002 | Suscripción procesamiento streaming | Streaming | V1/V4 | Pub/Sub | Subscription | dev | rs-dev-str-ps-events-dataflow | global | n/a | ingest | n/a | internal | RetailSmart | script | approved |
| RS-STR-003 | Tópico Insights Retail | Streaming | V1/V4 | Pub/Sub | Topic | dev | rs-dev-str-ps-insights | global | n/a | serving | n/a | internal | RetailSmart | script | approved |
| RS-DATA-001 | Bronze Eventos Raw | Data | V1/V4 | Cloud Storage | Bucket | dev | rs-dev-data-gcs-bronze-<suffix> | regional | configurable | n/a | bronze | internal | RetailSmart | script | approved |
| RS-DATA-002 | Silver Eventos Curados | Data | V1/V4 | Cloud Storage | Bucket | dev | rs-dev-data-gcs-silver-<suffix> | regional | configurable | n/a | silver | internal | RetailSmart | script | approved |
| RS-STR-004 | Dataflow Staging/Temp | Streaming | Transversal | Cloud Storage | Bucket | dev | rs-dev-str-gcs-dataflow-<suffix> | regional | configurable | technical | n/a | internal | RetailSmart | script | approved |
| RS-DATA-003 | Gold Insights Retail | Data | V1/V4 | BigQuery | Dataset | dev | rs_dev_gold | regional | configurable | serving | gold | internal | RetailSmart | script | approved |
| RS-SEC-001 | Identidad Dataflow | Security | Transversal | IAM | Service Account | dev | rs-dev-str-sa-dataflow | global | n/a | security | n/a | internal | RetailSmart | script | approved |
| RS-SEC-002 | Identidad de aprovisionamiento | Security | Transversal | IAM | Service Account | dev | rs-dev-sec-sa-deployer | global | n/a | security | n/a | internal | RetailSmart | script | approved |


Los nueve recursos del Streaming Core de la fase 2 están aprobados para implementación; este estado no implica que estén desplegados.

- `scope` admite `global`, `regional` o `multi-region`. Para buckets y dataset se adopta scope regional con location externa compatible; cambiar a multi-region requiere actualizar primero el catálogo.
- Pub/Sub usa scope global y location `n/a`. La residencia de mensajes se define por configuración específica de los tópicos.
- RS-STR-002 consume exclusivamente RS-STR-001. Sus propiedades deben externalizarse en configuración, sin valores hardcodeados en scripts.
- No se crea una subscription de Insights en este corte: no está catalogada.
- `<suffix>` se resuelve mediante configuración externa estable, sin alterar el patrón aprobado.
- `layer` solo admite `bronze`, `silver`, `gold` o `n/a` cuando no aplica. `role` solo admite `ingest`, `serving`, `technical`, `security` o `n/a` cuando no aplica. Bronze y Silver no reciben un role adicional en este corte.
- RS-SEC-002 es la Service Account concreta `rs-dev-sec-sa-deployer`. Una identidad inicial existente y autorizada realiza su bootstrap; no se crea otra identidad de aplicación para ello.
- IAM se limita a las cuentas deployer y Dataflow y a los permisos necesarios sobre los recursos catalogados, con mínimo privilegio. No se crean claves de cuentas ni roles personalizados en este corte.
- Las identidades administradas por Google que resulten necesarias al habilitar APIs son dependencias del servicio, no nuevas identidades de aplicación. No se crean manualmente ni se eliminan mediante destroy.

---

### IAM aprobado para FASE 2.2

- RS-SEC-001 se crea sin roles runtime. Los permisos de Dataflow, Pub/Sub,
  Storage y BigQuery se difieren a sus fases.
- RS-SEC-002 recibe `roles/iam.serviceAccountViewer` sobre cada una de las dos
  cuentas, exclusivamente para `get` y `getIamPolicy` usados en validación.
  La implementación verifica previamente que el rol incluya ambos permisos;
  no amplía roles automáticamente si la definición cambia.
- `BOOTSTRAP_ACCOUNT` recibe `roles/iam.serviceAccountTokenCreator` únicamente
  sobre RS-SEC-002. No se crean claves.
- El bootstrap usa sus permisos existentes para crear cuentas y gestionar
  estos bindings; el deployer no administra IAM de proyecto ni sus propios permisos.
- Las Service Accounts no soportan labels convencionales: Component ID y propósito
  se registran en displayName, y la metadata de labels en description.
- El futuro lanzador de jobs podría necesitar `roles/iam.serviceAccountUser`
  sobre RS-SEC-001; no se concede en 2.2.

---

### Diseño aprobado para FASE 2.3 — Pub/Sub

- Se aprovisionan exclusivamente RS-STR-001, RS-STR-002 y RS-STR-003.
- RS-STR-002 es pull sobre RS-STR-001: ack de 60 segundos, retención de 3600
  segundos, sin retener mensajes confirmados, expiración de 604800 segundos
  de inactividad y retry inmediato. Todos estos valores son configuración externa.
- Ordering, exactly-once, DLQ, filtros, push y export quedan deshabilitados.
  No se crean schemas, snapshots, subscriptions adicionales ni auditoría.
- No se configura Message Storage Policy ni variables de residencia en este
  corte. Pub/Sub conserva la política por defecto que determine GCP/organización;
  scope global y location n/a no cambian.
- Se aprueba temporalmente `roles/pubsub.editor` para RS-SEC-002 a nivel proyecto.
  Es aprovisionamiento más amplio que mínimo estricto: permite otras operaciones
  Pub/Sub además de las usadas por scripts y debe revisarse posteriormente.
  No se concede administración IAM al deployer ni roles runtime a RS-SEC-001.
  Desde FASE 2.6, cada operación concede el binding solo si falta y retira en
  finally exclusivamente el creado por esa operación, confirmando su ausencia.
  Los bindings preexistentes se conservan y se reportan. Las métricas separan
  changes permanentes de iam_changes temporales; validate puede usar IAM temporal.
- La retención de una hora puede descartar eventos no consumidos. La expiración
  permite eliminar subscriptions inactivas; deploy las recrea. Revisar ambos
  parámetros antes del E2E. No hay cómputo, retención de tópico ni features pagas
  adicionales. El tráfico futuro puede generar cargos.
- Deploy/validate/destroy se implementan en `infra/pubsub/`, vinculados al catálogo.
  Destroy requiere ejecución explícita y elimina la subscription antes de tópicos.

---

### Diseño aprobado para FASE 2.4 — Storage

- Solo RS-DATA-001, RS-DATA-002 y RS-STR-004, físicamente separados y con sufijo
  externo. Nombres resueltos para dev/rsg: `rs-dev-data-gcs-bronze-rsg`,
  `rs-dev-data-gcs-silver-rsg` y `rs-dev-str-gcs-dataflow-rsg`.
- Scope regional, location `us-central1` por configuración, clase `STANDARD`,
  acceso uniforme habilitado y Public Access Prevention `enforced`.
- Cifrado administrado por Google; sin CMEK, versioning, Bucket Lock,
  retention policy, Autoclass, replicación adicional ni cómputo.
- Bronze: soft delete de 604800 segundos (7 días), sin lifecycle. Permite
  recuperar originales tras eliminación accidental; los datos eliminados pueden
  seguir generando costo durante recuperación.
- Silver: soft delete deshabilitado, sin lifecycle; se reconstruye desde Bronze.
- Dataflow Staging/Temp: soft delete deshabilitado y una sola regla lifecycle
  `Delete` con `age=1`, para controlar acumulación técnica. La eliminación es
  asíncrona, no un temporizador exacto; revisar antes de jobs prolongados.
- RS-SEC-002 usa `roles/storage.admin` temporal a nivel proyecto, más amplio que
  mínimo estricto. Bootstrap asigna el binding, impersona al deployer y retira en
  finally únicamente el binding que faltaba al comenzar y creó la operación.
  Los bindings preexistentes se conservan. No se otorgan permisos Storage a
  RS-SEC-001; los accesos runtime quedan para el diseño Dataflow.
- La implementación usa Python, gcloud para autenticación/IAM y la JSON API de
  Cloud Storage para crear atómicamente buckets con labels y protecciones.
  No se habilitan APIs adicionales ni se generan objetos de prueba o carpetas.
- `changes` cuenta cambios persistentes de buckets; `iam_changes` registra por
  separado asignación y retirada del permiso temporal. Reejecutar debe dejar
  `changes=0` y la política IAM inicial restaurada.
- Destroy previsualiza por defecto; eliminar datos requiere `--purge` además de
  `--execute-destroy`. No se desactiva soft delete de Bronze para forzar borrado:
  su recuperación y costo residual continúan según la política aprobada.

---

### Diseño aprobado para FASE 2.5 — BigQuery Gold

- Solo RS-DATA-003, dataset `rs_dev_gold`, scope regional, `us-central1` externo,
  cifrado Google-managed y clasificación `internal`. Se crea vacío, con labels
  del catálogo, incluyendo role=serving, layer=gold y vertical=multi.
- No se configuran expiraciones predeterminadas de tablas o particiones: ambas
  son null/ausentes. Gold es persistente; la retención futura se define por tabla
  o producto. No se añaden variables de expiración al env.
- No se envía ni modifica storageBillingModel; se conserva el comportamiento por
  defecto de BigQuery. Las futuras consultas se plantean on-demand, sin crear
  reservations, slots, BI Engine, materialized views, cargas ni jobs en esta fase.
  No se certifica pricing efectivo de jobs futuros sin revisar asignaciones
  heredadas; no se habilita Reservation API para este corte.
- RS-SEC-002 usa roles/bigquery.user temporal en proyecto únicamente al necesitar
  crear el dataset; incluye capacidad de jobs no utilizada y es más amplio que
  mínimo estricto. Data Owner temporal solo sobre rs_dev_gold para sus operaciones.
  No se otorgan BigQuery Admin, roles básicos Owner/Editor ni permisos runtime.
- Para un dataset nuevo, access explícito conserva a los administradores ya
  existentes del proyecto (specialGroup projectOwners). OWNER en esta ACL es el
  alias de BigQuery Data Owner a nivel dataset, no un grant de roles/owner al
  proyecto. No se añaden projectReaders/projectWriters ni accesos públicos.
- El código detecta un eventual Data Owner automático del creador y compara ACL
  con el estado inicial. Antes de retirarlo verifica permisos administrativos
  efectivos del bootstrap mediante projects.testIamPermissions y lectura del
  dataset. La retirada se ejecuta con credenciales bootstrap y precondición etag,
  se confirma con lectura posterior y conserva todos los accesos preexistentes.
- Finally limpia los accesos creados; intenta cleanup de proyecto aunque falle
  el del dataset. Si no puede demostrar administración bootstrap, no retira el
  acceso del dataset a ciegas: informa error y detiene la fase, sin ampliar roles.
- Deploy/validate/destroy usan scripts Python y JSON APIs con autenticación/IAM
  vía gcloud. No ejecutan SQL ni bq jobs, ni habilitan APIs adicionales.
- Destroy previsualiza por defecto, solo elimina el dataset vacío con
  deleteContents=false y rechaza tablas, views, modelos o rutinas. Sin purga.

---

## 3. Componentes de arquitectura aún no aprovisionados en la fase 2

Estos componentes existen en la arquitectura, pero no deben implementarse todavía en el primer corte de infraestructura:

| Component ID | Componente | Motivo |
|---|---|---|
| RS-STR-010 | [Stream Processor] Ingesta Streaming | Se implementará con Beam/Dataflow en Paso 4 |
| RS-STR-011 | Raw Event Writer | Parte del pipeline |
| RS-STR-012 | Silver Event Writer | Parte del pipeline |
| RS-STR-013 | [Stream Processor] Procesamiento Tiempo Real | Paso 4 |
| RS-STR-014 | Gold Insights Writer | Parte del pipeline |
| RS-OBS-001 | Tópico Auditoría de Procesamiento | Se habilitará cuando se cierre estrategia de observabilidad/auditoría |
| RS-GOV-001 | Catálogo / Gobierno de Datos | Workstream posterior; debe mantenerse contemplado desde diseño |

---

## 4. Contratos streaming asociados

| Evento | Productor de Arquitectura | Tópico destino |
|---|---|---|
| clic_event | Aplicaciones de Canal Web/App/POS | RS-STR-001 |
| iot_event | Sensores IoT de Tienda | RS-STR-001 |
| stock_event | Estantería Inteligente | RS-STR-001 |
| location_event | Tracking Logístico | RS-STR-001 |
| telemetry_event | Cámaras Frigoríficas | RS-STR-001 |
| warehouse_sensor_event | Sensores de Almacén | RS-STR-001 |

---

## 5. Labels esperados

Conservar `V1/V4` en el catálogo y usar `vertical=multi` en GCP. Omitir `vertical` para componentes transversales sin vertical específica. Omitir labels cuyo valor en catálogo sea `n/a`; no publicar `n/a` como valor. Aplicar labels solo si el servicio los admite.

Ejemplo para `RS-STR-001`:

```text
project=retailsmart
environment=dev
domain=streaming
managed_by=script
component_id=rs-str-001
role=ingest
vertical=multi
```

Ejemplo para `RS-DATA-001`:

```text
project=retailsmart
environment=dev
domain=data
managed_by=script
component_id=rs-data-001
layer=bronze
vertical=multi
data_classification=internal
```

---

## 6. Estados permitidos

| Estado | Significado |
|---|---|
| proposed | definido pero no aprobado |
| approved | aprobado para implementación |
| deployed | desplegado |
| validated | probado |
| deprecated | en retiro |
| removed | eliminado |

---

## 7. Regla de cambio

Si Codex propone un recurso adicional:

1. identificar qué componente de arquitectura representa;
2. justificar por qué es necesario;
3. registrar primero en este catálogo;
4. aprobar;
5. recién después implementar.

No crear infraestructura no catalogada.

---

## 8. Próximas extensiones

Este catálogo crecerá después con:

- Batch;
- Dataproc / Spark;
- Composer / Airflow;
- BigQuery marts;
- Cloud Run API;
- Looker;
- Gobierno;
- Catálogo;
- Seguridad;
- Observabilidad;
- ML.

No deben incorporarse todavía a la fase 2 de Streaming salvo dependencias estrictamente necesarias.


## Operación integrada — FASE 2.6

El coordinador reutiliza los módulos existentes en orden Configuration →
Bootstrap/APIs → IAM Foundation → Pub/Sub → Storage → BigQuery. No incorpora
recursos al catálogo. Ante fallo limpia IAM temporal, conserva recursos válidos y
omite fases dependientes, sin rollback destructivo.

Destroy es preview por defecto; antes de borrar comprueba todos los módulos.
Con ejecución explícita elimina Gold vacío, buckets vacíos, subscription y tópicos,
en ese orden. Rechaza artefactos BigQuery, objetos Storage y subscriptions externas.
No admite purge/force ni elimina identidades, IAM Foundation, APIs, proyecto o
billing. Los permisos preexistentes se conservan. Los prechecks no sustituyen las
protecciones de cada módulo frente a cambios concurrentes.
