# RetailSmart / Lumina Retail — Architecture Overview

## 1. Propósito

RetailSmart implementa una plataforma de datos para soportar una operación omnicanal y cuatro verticales del caso:

1. **Decisiones en tiempo real**
2. **Planes diarios de inventario**
3. **Informes operativos**
4. **Mantenimiento proactivo**

La Arquitectura de Solución es la **fuente de verdad** para la implementación. Si durante el desarrollo se requiere cambiar un componente, evento, flujo o tecnología, primero debe registrarse la decisión, actualizarse la Arquitectura de Solución y el catálogo/documentación, y recién después modificarse la implementación.

---

## 2. Principio E2E

```text
Aplicaciones / dispositivos de origen
        ↓
Ingesta Streaming + Batch
        ↓
Bronze — datos originales
        ↓
Procesamiento / curación
        ↓
Silver — datos curados e integrados
        ↓
Procesamiento especializado
Tiempo real · Predictivo · OLAP
        ↓
Gold — productos de datos
        ↓
Tópicos · APIs · BI · Apps consumidoras
```

---

## 3. Fuentes modeladas

### Streaming

- **Aplicaciones de Canal (Web / App / POS)**
  - `clic_event`
- **Sensores IoT de Tienda**
  - `iot_event`
- **Estantería Inteligente**
  - `stock_event`
- **Tracking Logístico**
  - `location_event`
- **Cámaras Frigoríficas**
  - `telemetry_event`
- **Sensores de Almacén**
  - `warehouse_sensor_event`

### Batch

La arquitectura contempla cargas batch asociadas a:

- ventas
- inventario
- tiendas
- benchmark / competencia
- otras fuentes externas definidas por el caso

Los nombres de flujo ya presentes en el diseño incluyen:

- `ventas_batch`
- `inventory_batch`
- `store_batch`
- `benchmark_batch`

---

## 4. Streaming E2E

```text
Productores
  ├─ clic_event
  ├─ iot_event
  ├─ stock_event
  ├─ location_event
  ├─ telemetry_event
  └─ warehouse_sensor_event
        ↓
Tópico Eventos Retail
        ↓
[Stream Processor] Ingesta Streaming
        ├─ Raw Event Writer → Bronze Eventos Raw
        └─ valid_event / curated_event
                 ↓
          Silver Event Writer
                 ↓
        Silver Eventos Curados
                 ↓
[Stream Processor] Procesamiento Tiempo Real
        ↓
Tópico Insights Retail
        ↓
Gold Insights Writer
        ↓
Gold Insights Retail
        ↓
Consumidores
```

La arquitectura también contiene:

- `Tópico Auditoría de Procesamiento`
- componentes de auditoría / observabilidad
- procesamiento de telemetría y mantenimiento predictivo

---

## 5. Batch E2E

```text
Fuentes Batch
    ↓
[Batch Job] Ingesta Batch
    ↓
Bronze Datos Batch
    ↓
[Batch Processor] Curación Batch
    ↓
Silver Datos Curados
    ↓
Procesamiento predictivo / OLAP
    ├─ Forecast / Planificación
    ├─ Operational Mart
    └─ Mantenimiento predictivo
    ↓
Gold
```

La orquestación batch está representada mediante:

- `[Orchestrator] Planificador Batch`

---

## 6. Capas Medallion

### Bronze
Datos originales, auditables y reejecutables.

Objetos modelados:
- `Bronze Eventos Raw`
- `Bronze Datos Batch`

### Silver
Datos validados, normalizados, deduplicados, curados e integrados.

Objetos modelados:
- `Silver Eventos Curados`
- `Silver Datos Curados`

### Gold
Productos de datos orientados a consumo.

Objetos modelados:
- `Gold Insights Retail`
- `Gold Planes Inventario`
- `Gold Operational Mart`
- `Gold Maintenance Insights`

---

## 7. Verticales y capacidades

### V1 — Decisiones en tiempo real
Usa principalmente:
- clicks
- IoT
- stock
- location
- procesamiento streaming
- `Tópico Insights Retail`
- `Gold Insights Retail`

Resultado:
- alertas
- recomendaciones
- insights operativos

### V2 — Planes diarios de inventario
Usa:
- históricos batch
- ventas
- inventario
- señales externas
- curación
- forecast
- planificación diaria

Resultado:
- pronóstico
- reposición sugerida
- stock objetivo
- riesgo de quiebre

### V3 — Informes operativos
Usa:
- datos Silver
- procesamiento analítico / OLAP
- `Gold Operational Mart`

Resultado:
- conversión
- ingresos
- costo de envío
- tiempo de entrega

### V4 — Mantenimiento proactivo
Usa:
- `telemetry_event`
- `warehouse_sensor_event`
- `location_event`
- análisis de telemetría
- modelo predictivo
- scoring de riesgo
- `Gold Maintenance Insights`

Resultado:
- anomalías
- riesgo de falla
- prioridad de intervención
- cuellos logísticos

---

## 8. Consumo

La arquitectura distingue dos patrones:

### Event-driven
`Tópico Insights Retail` → aplicaciones consumidoras operativas.

### Consulta síncrona
Productos Gold → API de acceso → aplicaciones consumidoras.

### Analítica
Gold / BigQuery → Reporting / BI.

---

## 9. Regla de implementación

Toda implementación debe poder responder:

1. ¿Qué componente de solución implementa?
2. ¿Qué vertical habilita?
3. ¿Qué dato recibe?
4. ¿Qué dato produce?
5. ¿Dónde persiste?
6. ¿Quién lo consume?
7. ¿Cómo se prueba?

No se deben crear componentes o eventos nuevos sin registrar previamente el cambio de arquitectura.

## Decisión arquitectónica — FASE 3.1: contratos de entrada v1

Diseño aprobado: conservar exactamente los seis eventos de entrada y el envelope
event_id, event_type, schema_version, event_timestamp, source y payload. Los
contratos representan hechos de origen, sin scenario, vertical, KPI, insights,
anomalías calculadas ni resultados de modelos. Fechas de evento en UTC; sin PII
real en ejemplos o pruebas. No se implementan productores ni publicación.

Se incorpora expected_delivery_timestamp a location_event como compromiso de
entrega informado por el origen, para habilitar medición posterior de retrasos.
No representa una ETA calculada ni una clasificación de retraso.

Trazabilidad aprobada: iot_event habilita V1 principal y V3 secundaria, sin V4;
telemetry_event y warehouse_sensor_event habilitan V1/V4 principales, sin V3 en
v1 por no existir un KPI operativo explícito. Las demás asociaciones conservan
la matriz aprobada. Las reglas de negocio, thresholds y modelos permanecen en
capas posteriores; la coherencia cantidad/capacidad es validación del hecho.

Gobierno: registrar decisión → actualizar Arquitectura de Solución → actualizar
catálogo/documentación → modificar implementación. Los contratos locales no
incorporan recursos GCP ni Schema Registry.

## Decisión arquitectónica — FASE 3.2: productor CLI unitario

Diseño aprobado: herramienta manual para las seis fuentes de entrada, sin
infraestructura nueva, generación masiva, consumo ni procesamiento. El flujo es
resolver configuración → construir → validate_event → serializar exactamente el
evento validado → comprobar OPERATOR_ACCOUNT → publicar en RS-STR-001 → confirmar
message_id. Dry-run termina tras mostrar el evento/destino, sin acceso a GCP.

OPERATOR_ACCOUNT identifica la cuenta existente de ejecución manual; permanece
separada de BOOTSTRAP_ACCOUNT (aprovisionamiento/administración), aunque puedan
coincidir inicialmente. No se usan deployer ni Dataflow como productor, no se
crean identidades y no se modifica IAM. Si falta pubsub.topics.publish sobre el
tópico aprobado, se detiene y se informa; un grant requiere aprobación separada.

Las seis fábricas construyen datos ficticios coherentes, sin dependencia runtime
de fixtures o ejemplos. Los schemas versionados y validate_event son la autoridad
sobre tipos, enums, restricciones y coherencia del contrato. Un compromiso nuevo
se asocia a una entrega ficticia nueva; no se desplaza el compromiso de una misma
entrega. La publicación gcloud queda desacoplada de la construcción de eventos.

## Decisión arquitectónica — FASE 3.3: escenarios sintéticos controlados

Diseño aprobado: seis perfiles pequeños (18/12/3/4/4/5 eventos; 46 en total),
valores fijos sin aleatoriedad, seed ni count. Contexto opcional de las fábricas
para run_id/start_time e identificadores determinísticos, compatible con el CLI
unitario. Schemas y validate_event permanecen sin cambios. Antes de cualquier
publicación explícita se valida y serializa todo el plan, incluidas relaciones
temporales y de identificadores. Dry-run predeterminado, completamente local.

NORMAL es un **baseline transversal de operación**: incluye las fuentes de las
cuatro verticales, sin representar un insight único compartido. DELIVERY_DELAY
se asocia solo a V1/V3 principales; no representa mantenimiento ni falla mecánica.
Telemetría y degradación de almacén mantienen V1/V4 principales, sin V3.

Los nombres de escenarios pertenecen al plan/reporte local y nunca al envelope,
payload, identificadores legibles ni atributos Pub/Sub. Se reutilizan las seis
fábricas, validate_event y el adaptador operativo OPERATOR_ACCOUNT/RS-STR-001.
No hay retries propios, rate control, ordering garantizado ni recursos nuevos.

Esta fase autoriza únicamente seis dry-runs, validación local de 46 eventos y
pruebas simuladas de publicación. Las publicaciones reales de escenarios quedan
pendientes de aprobación separada tras revisar el resultado local. Sin consumo,
Producer Console, Dataflow ni procesamiento downstream.


## Decisión arquitectónica — Source Emulator V1 Streaming

Solicitud aprobada: aplicación local Python/Streamlit que representa las seis
fuentes de solución y reutiliza fábricas, perfiles, contratos y publicación.
Evoluciona la consola prevista en PASO 5 como Source Emulator, sin crear un
componente GCP ni modificar el flujo de ingesta. No se implementan Batch o Dataflow.

El Producer Engine es independiente de Streamlit: un worker controlado por
fuente, sin cola acumulativa, ritmo máximo configurable con techo de 20 evt/s
por fuente, límite de ejecución y lease de actividad de la sesión. STOP impide
nuevos envíos y espera la operación en curso, con timeout; los threads salen al
vencer lease o ventana de ejecución. El cierre del navegador se detecta por
expiración del lease, no instantáneamente. El cierre explícito detiene el engine.

La publicación del CLI continúa usando gcloud. El emulador reutiliza publish
con un transporte REST intercambiable, token operativo obtenido por gcloud y
retenido solo en memoria, sin retries ni impersonación. Destino único RS-STR-001,
OPERATOR_ACCOUNT y permisos existentes. Un fallo detiene la fuente sin reenvío.
El rate es objetivo/máximo; el ritmo observado depende de latencia de Pub/Sub.

Modo libre: fábricas existentes, hechos independientes con IDs nuevos. Perfiles:
plan completo prevalidado y finito; un único escenario compartido por ejecución
preserva correlaciones entre fuentes. Solo se habilitan fuentes presentes en el
perfil; no se mezclan escenarios activos. Los timestamps siguen el reloj
sintético original del perfil; el rate regula emisión, sin reescribir los hechos.
La UI identifica ese reloj simulado. La repetición inicia otro run_id, nunca
reutiliza los IDs de una ejecución anterior. Escenario sigue fuera del evento.

Overview/Streaming/Batch/Activity separan presentación de catálogo de fuentes y
engine. Batch solo muestra Coming next. Registro en memoria de 50 eventos, sin
tokens, credenciales o ackId. La demo autorizada publica stock y location a
1 evt/s durante cinco segundos cada uno y cuatro muestras de TELEMETRY_ANOMALY;
no consume mensajes, no asigna IAM ni habilita servicios adicionales.
