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
- La retención de una hora puede descartar eventos no consumidos. La expiración
  permite eliminar subscriptions inactivas; deploy las recrea. Revisar ambos
  parámetros antes del E2E. No hay cómputo, retención de tópico ni features pagas
  adicionales. El tráfico futuro puede generar cargos.
- Deploy/validate/destroy se implementan en `infra/pubsub/`, vinculados al catálogo.
  Destroy requiere ejecución explícita y elimina la subscription antes de tópicos.

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
