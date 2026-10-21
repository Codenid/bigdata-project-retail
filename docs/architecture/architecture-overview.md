# RetailSmart / Lumina Retail — Architecture Overview

## 1. Propósito

RetailSmart implementa una plataforma de datos para soportar una operación omnicanal y cuatro verticales del caso:

1. **Decisiones en tiempo real**
2. **Planes diarios de inventario**
3. **Informes operativos**
4. **Mantenimiento proactivo**

La arquitectura es la **fuente de verdad** para la implementación. Si durante el desarrollo se requiere cambiar un componente, evento, flujo o tecnología, primero debe registrarse la decisión y actualizarse la arquitectura.

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

1. ¿Qué componente ArchiMate implementa?
2. ¿Qué vertical habilita?
3. ¿Qué dato recibe?
4. ¿Qué dato produce?
5. ¿Dónde persiste?
6. ¿Quién lo consume?
7. ¿Cómo se prueba?

No se deben crear componentes o eventos nuevos sin registrar previamente el cambio de arquitectura.
