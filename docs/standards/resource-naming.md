# RetailSmart — Resource Naming Standard

## 1. Objetivo

Definir un estándar simple, empresarial y consistente para identificar y nombrar los recursos de RetailSmart en GCP.

Este estándar debe revisarse antes de crear cualquier recurso.

La Arquitectura de Solución es la fuente de verdad. El nombre físico en GCP debe derivarse de un componente previamente definido en el diseño y registrado en el Resource Catalog.

---

## 2. Dos niveles de identificación

### 2.1 Component ID lógico

Formato:

```text
RS-<DOMINIO>-<NNN>
```

Ejemplos:

```text
RS-STR-001
RS-DATA-001
RS-GOV-001
RS-SEC-001
```

Este identificador se usa en:
- documentación;
- catálogo;
- trazabilidad Arquitectura de Solución → GCP;
- labels;
- evidencias;
- pruebas.

### 2.2 Nombre físico GCP

Patrón general:

```text
rs-<env>-<dominio>-<tipo>-<proposito>
```

Ejemplos:

```text
rs-dev-str-ps-events
rs-dev-str-ps-insights
rs-dev-data-gcs-bronze
rs-dev-data-gcs-silver
```

Para servicios con restricciones distintas, el patrón se adapta manteniendo la misma semántica.

Ejemplo BigQuery:

```text
rs_dev_gold
```

---

## 3. Abreviaturas

### Proyecto
| Código | Significado |
|---|---|
| rs | RetailSmart |

### Entorno
| Código | Significado |
|---|---|
| dev | Desarrollo |
| tst | Pruebas |
| prd | Producción |

### Dominio
| Código | Significado |
|---|---|
| str | Streaming |
| bat | Batch |
| data | Datos / Storage |
| ml | Machine Learning |
| api | APIs / Exposición |
| gov | Gobierno |
| sec | Seguridad |
| obs | Observabilidad |

### Tipo de recurso
| Código | Recurso |
|---|---|
| ps | Pub/Sub |
| gcs | Cloud Storage |
| bq | BigQuery |
| df | Dataflow |
| sa | Service Account |
| cr | Cloud Run |
| dp | Dataproc |
| cmp | Composer |

---

## 4. Reglas generales

1. Usar minúsculas en nombres físicos.
2. Evitar espacios.
3. Evitar nombres ambiguos como `bucket1`, `topic-test`, `data-new`.
4. El propósito debe expresar la función del recurso.
5. No incluir nombres de personas.
6. No incluir secretos ni información sensible.
7. El entorno debe estar explícito cuando el servicio lo permita.
8. No crear recursos fuera del Resource Catalog.
9. No renombrar un recurso sin actualizar:
   - arquitectura;
   - catálogo;
   - configuración;
   - scripts;
   - documentación.
10. Los nombres deben mantenerse lo más cortos posible sin perder significado.

---

## 5. Labels estándar

Cuando el servicio GCP permita labels, usar como mínimo:

```text
project=retailsmart
environment=dev
domain=<dominio>
managed_by=script
component_id=<component-id-normalizado>
```

Cuando aplique:

```text
layer=bronze|silver|gold
role=ingest|serving|technical|security
vertical=v1|v2|v3|v4|multi
data_classification=public|internal|confidential|restricted
```

Ejemplo:

```text
project=retailsmart
environment=dev
domain=streaming
managed_by=script
component_id=rs-str-001
role=ingest
vertical=multi
```

---

El catálogo conserva el detalle completo de verticales, por ejemplo `V1/V4`. Para múltiples verticales, usar `vertical=multi`; para componentes transversales sin vertical específica, omitir este label. Aplicar labels únicamente donde el servicio los soporte.

## 6. Convención de capas y roles

| Capa | Valor |
|---|---|
| Bronze | bronze |
| Silver | silver |
| Gold | gold |

`layer` expresa exclusivamente la capa Medallion y admite `bronze`, `silver` o `gold`. Si no aplica, registrar `n/a` en catálogo y omitir el label.

`role` expresa la función y admite `ingest`, `serving`, `technical` o `security`. Si no aplica, registrar `n/a` en catálogo y omitir el label. No usar estos valores como `layer`.

Las capas y los roles son conceptos independientes; no se infiere un role a partir de una capa.

Ejemplos:

```text
rs-dev-data-gcs-bronze
rs-dev-data-gcs-silver
rs_dev_gold
```

---

## 7. Región y location

La región no debe codificarse obligatoriamente en el nombre del recurso.

Debe definirse mediante configuración:

```text
GCP_REGION
GCP_LOCATION
```

Esto evita acoplar nombres físicos a una región concreta y facilita recrear el entorno.

Si un servicio exige unicidad global, puede añadirse un sufijo controlado por configuración.

Ejemplo:

```text
rs-dev-data-gcs-bronze-<project-suffix>
```

---

## 8. Recursos globales y regionales

Cada recurso debe registrar en el catálogo:

- `scope`: global / regional / multi-region;
- `location`;
- justificación si aplica.

Para este corte, buckets y dataset se planifican con `scope=regional` y una location regional externa compatible. Una ubicación multi-region requiere actualizar el scope del catálogo antes del deploy.

Los tópicos y subscriptions Pub/Sub tienen `scope=global` y `location=n/a`. La residencia de mensajes se configura mediante una política específica del tópico, independiente de la location del recurso. Las Service Accounts tienen `scope=global` y `location=n/a`.

Las propiedades de las subscriptions (ack deadline, retención y expiración, entre otras que se utilicen) deben definirse en configuración externa; los scripts no deben hardcodearlas.

No asumir que todos los servicios GCP comparten el mismo modelo de localización.

---

## 9. Ejemplos válidos

```text
rs-dev-str-ps-events
rs-dev-str-ps-insights
rs-dev-data-gcs-bronze
rs-dev-data-gcs-silver
rs-dev-str-gcs-dataflow
rs_dev_gold
rs-dev-str-sa-dataflow
```

---

## 10. Ejemplos inválidos

```text
topic1
bucket-final
retail-test2
winston-bucket
data-new
bigquerygoldprod
```

Motivos:
- no permiten identificar dominio o entorno;
- no expresan propósito;
- incluyen nombres personales;
- no siguen patrón consistente.

---

## 11. Regla operativa

Antes de crear cualquier recurso:

```text
Arquitectura de Solución
   ↓
Component ID
   ↓
Resource Catalog
   ↓
Naming Standard
   ↓
Config
   ↓
Script
   ↓
Deploy
   ↓
Validate
```

Si el recurso no está registrado en el catálogo, no debe ser creado.
