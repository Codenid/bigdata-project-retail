# RetailSmart — Streaming Contracts v1

## Estado

**Borrador controlado por arquitectura.**

Los nombres de eventos provienen del ArchiMate actual. No se agregan eventos nuevos en esta versión.

---

## Envelope común propuesto

Todos los eventos pueden compartir un envelope común para simplificar validación y trazabilidad:

```json
{
  "event_id": "evt-000001",
  "event_type": "stock_event",
  "schema_version": "1.0",
  "event_timestamp": "2026-10-21T12:00:00Z",
  "source": "smart_shelf",
  "payload": {}
}
```

| Campo | Tipo | Obligatorio | Uso |
|---|---|---:|---|
| event_id | string | Sí | deduplicación / trazabilidad |
| event_type | string | Sí | enrutamiento |
| schema_version | string | Sí | evolución de contrato |
| event_timestamp | timestamp | Sí | ventanas y secuencia temporal |
| source | string | Sí | productor |
| payload | object | Sí | atributos del evento |

> El envelope es una decisión de implementación compatible con los eventos del diseño; no cambia los nombres definidos en ArchiMate.

---

# 1. `clic_event`

**Productor:** Aplicaciones de Canal (Web / App / POS)

### Propósito
Capturar interacción digital para:
- tiempo real;
- señales de demanda;
- conversión / comportamiento.

### Payload propuesto

```json
{
  "customer_id": "CUS-1001",
  "session_id": "SES-9001",
  "product_id": "SKU-0042",
  "action": "VIEW_PRODUCT",
  "channel": "MOBILE",
  "store_id": "LIM-01"
}
```

### Campos

| Campo | Tipo | Uso |
|---|---|---|
| customer_id | string | análisis por cliente |
| session_id | string | sesión/funnel |
| product_id | string | interés por producto |
| action | string | click / view / search / add-to-cart |
| channel | string | WEB / MOBILE / POS |
| store_id | string | contexto de tienda |

---

# 2. `iot_event`

**Productor:** Sensores IoT de Tienda

### Propósito
Capturar eventos generales de dispositivos IoT en tienda para decisiones operativas en tiempo real.

### Payload propuesto

```json
{
  "device_id": "IOT-001",
  "store_id": "LIM-01",
  "metric": "OCCUPANCY",
  "value": 42,
  "unit": "COUNT",
  "status": "ACTIVE"
}
```

| Campo | Tipo | Uso |
|---|---|---|
| device_id | string | identificación de dispositivo |
| store_id | string | contexto |
| metric | string | tipo de medición |
| value | number | valor |
| unit | string | unidad |
| status | string | estado del dispositivo |

---

# 3. `stock_event`

**Productor:** Estantería Inteligente

### Propósito
Detectar:
- stock bajo;
- riesgo de quiebre;
- señales para reposición y demanda.

### Payload propuesto

```json
{
  "store_id": "LIM-01",
  "product_id": "SKU-0042",
  "shelf_id": "SHELF-17",
  "stock_quantity": 4,
  "stock_capacity": 30
}
```

| Campo | Tipo | Uso |
|---|---|---|
| store_id | string | tienda |
| product_id | string | producto |
| shelf_id | string | estantería |
| stock_quantity | integer | stock actual |
| stock_capacity | integer | capacidad |

---

# 4. `location_event`

**Productor:** Tracking Logístico

### Propósito
Medir:
- posición;
- avance de entrega;
- retrasos;
- tiempos de entrega;
- cuellos de botella.

### Payload propuesto

```json
{
  "delivery_id": "DEL-1009",
  "order_id": "ORD-7781",
  "vehicle_id": "VEH-08",
  "latitude": -12.087,
  "longitude": -77.051,
  "delivery_status": "IN_TRANSIT",
  "speed_kmh": 18.5
}
```

| Campo | Tipo | Uso |
|---|---|---|
| delivery_id | string | entrega |
| order_id | string | correlación con pedido |
| vehicle_id | string | unidad logística |
| latitude | number | posición |
| longitude | number | posición |
| delivery_status | string | estado |
| speed_kmh | number | movilidad / retrasos |

---

# 5. `telemetry_event`

**Productor:** Cámaras Frigoríficas

### Propósito
Detectar:
- comportamiento anómalo;
- degradación;
- riesgo de falla.

### Payload propuesto

```json
{
  "device_id": "CAM-FRIO-018",
  "warehouse_id": "WH-LIM-02",
  "metric": "TEMPERATURE",
  "value": 9.2,
  "unit": "CELSIUS",
  "status": "ACTIVE"
}
```

| Campo | Tipo | Uso |
|---|---|---|
| device_id | string | activo |
| warehouse_id | string | almacén |
| metric | string | medición |
| value | number | valor |
| unit | string | unidad |
| status | string | estado |

---

# 6. `warehouse_sensor_event`

**Productor:** Sensores de Almacén

### Propósito
Capturar condiciones y estado operativo de almacenes/equipos para mantenimiento proactivo.

### Payload propuesto

```json
{
  "sensor_id": "WS-009",
  "warehouse_id": "WH-LIM-02",
  "metric": "VIBRATION",
  "value": 8.7,
  "unit": "MM_S",
  "equipment_id": "CONVEYOR-12",
  "status": "ACTIVE"
}
```

| Campo | Tipo | Uso |
|---|---|---|
| sensor_id | string | sensor |
| warehouse_id | string | almacén |
| equipment_id | string | equipo monitoreado |
| metric | string | tipo de medición |
| value | number | valor |
| unit | string | unidad |
| status | string | estado |

---

## Escenarios sintéticos

Los generadores no deben producir únicamente ruido aleatorio.

Escenarios mínimos posteriores:

- `NORMAL`
- `HIGH_DEMAND`
- `LOW_STOCK`
- `DELIVERY_DELAY`
- `TELEMETRY_ANOMALY`
- `WAREHOUSE_EQUIPMENT_DEGRADATION`

Estos escenarios deberán generar secuencias coherentes que permitan demostrar la historia E2E.
