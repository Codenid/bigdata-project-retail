# RetailSmart — Source to Vertical Matrix

## Objetivo

Garantizar que cada fuente y cada evento tenga utilidad dentro del caso de negocio.
La Arquitectura de Solución y el diseño aprobado de FASE 3.1 rigen esta matriz.
IoT de tienda no se asocia a V4 en v1. Telemetría y sensores de almacén no se
asocian a V3 mientras no exista un KPI operativo explícitamente definido.

Leyenda:

- **P** = uso principal
- **S** = uso secundario / señal complementaria
- `—` = no requerido directamente

| Fuente / Evento | V1 Tiempo Real | V2 Inventario | V3 Informes Operativos | V4 Mantenimiento |
|---|:---:|:---:|:---:|:---:|
| `clic_event` | P | S | P | — |
| `iot_event` | P | — | S | — |
| `stock_event` | P | P | S | — |
| `location_event` | P | — | P | P |
| `telemetry_event` | P | — | — | P |
| `warehouse_sensor_event` | P | — | — | P |
| ventas batch | — | P | P | — |
| inventario batch | — | P | P | — |
| tiendas batch | S | P | P | S |
| benchmark batch | — | — | P | — |

---

## V1 — Decisiones en tiempo real

### Datos
- clicks
- IoT
- stock
- ubicación
- telemetría

### Procesamiento
Streaming de baja latencia.

### Resultado
- alertas
- recomendaciones
- insights

### Consumidores
Apps operativas / consumidores de `Tópico Insights Retail`.

---

## V2 — Planes diarios de inventario

### Datos
- ventas históricas
- inventario
- stock
- señales de demanda
- fuentes externas

### Resultado
- pronóstico de demanda
- reposición sugerida
- riesgo de quiebre

### Data Product
`Gold Planes Inventario`

---

## V3 — Informes operativos

### Datos
- comportamiento digital
- ventas
- logística
- entregas
- benchmark

### Resultado
- conversión
- ingresos
- costo de envío
- tiempos de entrega

### Data Product
`Gold Operational Mart`

---

## V4 — Mantenimiento proactivo

### Datos
- `telemetry_event`
- `warehouse_sensor_event`
- `location_event`

### Resultado
- anomalías
- riesgo de falla
- prioridad de mantenimiento
- cuellos de botella logísticos

### Data Product
`Gold Maintenance Insights`

---

## Regla para generación sintética

Antes de agregar un campo a un evento, responder:

1. ¿Qué vertical lo necesita?
2. ¿Qué transformación lo consume?
3. ¿Qué métrica / insight / predicción habilita?
4. ¿Quién consume ese resultado?

Si no existe respuesta clara, el campo no debe agregarse al contrato v1.
