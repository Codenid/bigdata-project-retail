# RetailSmart — Contratos Streaming v1

Estado: diseño aprobado de FASE 3.1. La Arquitectura de Solución es la fuente de
verdad; véase la [decisión arquitectónica](../architecture/architecture-overview.md). No se
renombran eventos ni se crean productores, publicación o recursos GCP.

## Envelope común

JSON Schema Draft 2020-12. Los seis eventos componen common-event.schema.json.
El envelope común no sustituye la validación con el schema específico.

| Campo | Tipo | Obligatorio | Uso |
|---|---|---|---|
| event_id | string | Sí | Identidad estable del hecho para deduplicación y trazabilidad |
| event_type | string | Sí | Uno de los seis nombres oficiales; coincide con su schema |
| schema_version | string, constante 1.0 | Sí | Selección explícita de contrato |
| event_timestamp | string UTC | Sí | Instante de ocurrencia en origen, no llegada a Pub/Sub |
| source | string, constante por evento | Sí | Productor lógico aprobado |
| payload | object | Sí | Hechos específicos de origen |

Las fechas admiten YYYY-MM-DDTHH:MM:SS[.fracción]Z, con calendario válido y
segundos 00–59; no se admiten offsets ni segundos intercalares en este perfil.
No se compara con el reloj actual: replays y compromisos vencidos son válidos.
Identificadores no vacíos y sin espacios; no se impone un prefijo de negocio.
Los opcionales se omiten si se desconocen; ningún campo declarado admite null.
No se permiten propiedades adicionales en envelope o payload. No se incluyen
scenario, vertical, KPI, insights, anomalías calculadas ni resultados de modelos.

## clic_event

Productor lógico: **Aplicaciones de Canal Web/App/POS**. source: `channel_app`.
Verticales: V1 P; V2 S; V3 P. P=principal; S=secundaria.

| Campo de payload | Tipo | Obligatorio | Ejemplo | Uso downstream |
|---|---|---|---|---|
| session_id | string | Sí | `"SES-9001"` | Agrupar navegación y funnel por sesión. |
| customer_id | string | No | `"CUS-SYN-1001"` | Recurrencia entre sesiones de una identidad ficticia; opcional. |
| product_id | string | Condicional: salvo SEARCH | `"SKU-0042"` | Interés por producto y correlación con stock; requerido salvo SEARCH. |
| action | string | Sí | `"VIEW_PRODUCT"` | Contabilizar interacciones e intención. |
| channel | string | Sí | `"MOBILE"` | Comparar comportamiento por canal. |
| store_id | string | No | `"LIM-01"` | Tienda asociada cuando es conocida; no inventar contexto. |

action: CLICK, VIEW_PRODUCT, SEARCH o ADD_TO_CART. channel: WEB, MOBILE o POS.
product_id es obligatorio salvo SEARCH. customer_id es ficticio y opcional;
store_id solo se informa si es conocido. Conversión a compra requiere futura
vinculación con pedidos/ventas; agregado al carrito no equivale a compra.

## iot_event

Productor lógico: **Sensores IoT de Tienda**. source: `store_iot_sensor`.
Verticales: V1 P; V3 S. P=principal; S=secundaria.

| Campo de payload | Tipo | Obligatorio | Ejemplo | Uso downstream |
|---|---|---|---|---|
| device_id | string | Sí | `"IOT-001"` | Serie temporal del dispositivo. |
| store_id | string | Sí | `"LIM-01"` | Agrupar y correlacionar por tienda. |
| metric | string | Sí | `"OCCUPANCY"` | Medición de ocupación. |
| value | integer | Sí | `42` | Ocupación observada; no representa visitantes únicos. |
| unit | string | Sí | `"COUNT"` | Unidad de conteo. |
| status | string | Sí | `"ACTIVE"` | Estado observado del dispositivo o sensor. |

metric=OCCUPANCY, unit=COUNT, value entero >=0; status ACTIVE/INACTIVE.
Una lectura INACTIVE no demuestra ocupación actual sin evaluar su vigencia.

## stock_event

Productor lógico: **Estantería Inteligente**. source: `smart_shelf`.
Verticales: V1 P; V2 P; V3 S. P=principal; S=secundaria.

| Campo de payload | Tipo | Obligatorio | Ejemplo | Uso downstream |
|---|---|---|---|---|
| store_id | string | Sí | `"LIM-01"` | Localizar disponibilidad y reposición. |
| product_id | string | Sí | `"SKU-0042"` | Correlacionar interés, stock y futuras ventas. |
| shelf_id | string | Sí | `"SHELF-17"` | Identificar posición física de la observación. |
| stock_quantity | integer | Sí | `4` | Snapshot de unidades disponibles; no son ventas ni movimientos. |
| stock_capacity | integer | Sí | `30` | Capacidad para calcular proporción de ocupación. |

stock_quantity entero >=0; stock_capacity entero >0. La validación semántica
exige stock_quantity <= stock_capacity. No se define un threshold de stock bajo.

## location_event

Productor lógico: **Tracking Logístico**. source: `logistics_tracking`.
Verticales: V1 P; V3 P; V4 P. P=principal; S=secundaria.

| Campo de payload | Tipo | Obligatorio | Ejemplo | Uso downstream |
|---|---|---|---|---|
| delivery_id | string | Sí | `"DEL-1009"` | Secuencia de observaciones de una entrega. |
| order_id | string | Sí | `"ORD-7781"` | Vincular con el pedido cuando exista su fuente. |
| vehicle_id | string | Sí | `"VEH-08"` | Analizar movilidad y cuellos logísticos. |
| latitude | number | Sí | `-12.087` | Latitud observada del vehículo; ejemplos ficticios. |
| longitude | number | Sí | `-77.051` | Longitud observada del vehículo; ejemplos ficticios. |
| delivery_status | string | Sí | `"IN_TRANSIT"` | Estado observado; DELIVERED usa timestamp de confirmación. |
| speed_kmh | number | Sí | `18.5` | Movilidad y detenciones observadas. |
| expected_delivery_timestamp | string UTC | Sí | `"2026-10-21T13:00:00Z"` | Compromiso informado por origen, no ETA recalculada; puede estar vencido. |

latitude entre -90 y 90; longitude entre -180 y 180; speed_kmh >=0.
Estados IN_TRANSIT/DELIVERED. En DELIVERED, event_timestamp es la confirmación.
expected_delivery_timestamp conserva el compromiso informado por origen, puede
estar vencido y no es una ETA calculada. Tiempo total de pedido requiere su
timestamp de creación en una fuente posterior.

## telemetry_event

Productor lógico: **Cámaras Frigoríficas**. source: `cold_room`.
Verticales: V1 P; V4 P. P=principal; S=secundaria.

| Campo de payload | Tipo | Obligatorio | Ejemplo | Uso downstream |
|---|---|---|---|---|
| device_id | string | Sí | `"CAM-FRIO-018"` | Serie temporal del activo frigorífico. |
| warehouse_id | string | Sí | `"WH-LIM-02"` | Contexto operativo de almacén. |
| metric | string | Sí | `"TEMPERATURE"` | Variable térmica observada. |
| value | number | Sí | `9.2` | Temperatura observada, incluidos valores negativos o anómalos. |
| unit | string | Sí | `"CELSIUS"` | Temperatura en grados Celsius. |
| status | string | Sí | `"ACTIVE"` | Estado observado del dispositivo o sensor. |

status ACTIVE/INACTIVE. metric=TEMPERATURE y unit=CELSIUS; se admiten temperaturas negativas.
Una medición anómala es un hecho válido. Los rangos operativos y los thresholds
pertenecen a capas posteriores y no se implementan en este contrato.

## warehouse_sensor_event

Productor lógico: **Sensores de Almacén**. source: `warehouse_sensor`.
Verticales: V1 P; V4 P. P=principal; S=secundaria.

| Campo de payload | Tipo | Obligatorio | Ejemplo | Uso downstream |
|---|---|---|---|---|
| sensor_id | string | Sí | `"WS-009"` | Serie temporal del sensor. |
| warehouse_id | string | Sí | `"WH-LIM-02"` | Localizar contexto operativo. |
| equipment_id | string | Sí | `"CONVEYOR-12"` | Agrupar sensores del mismo equipo. |
| metric | string | Sí | `"VIBRATION"` | Variable de condición observada. |
| value | number | Sí | `8.7` | Velocidad de vibración observada; valores altos son válidos. |
| unit | string | Sí | `"MM_S"` | Velocidad de vibración en milímetros por segundo. |
| status | string | Sí | `"ACTIVE"` | Estado observado del dispositivo o sensor. |

status ACTIVE/INACTIVE. metric=VIBRATION y unit=MM_S; value >=0.
Una medición anómala es un hecho válido. Los rangos operativos y los thresholds
pertenecen a capas posteriores y no se implementan en este contrato.

## Correlación y límites

| Clave | Uso | Límite |
|---|---|---|
| event_id | Deduplicación de reentregas | Un hecho nuevo recibe otro ID; reintentos conservan contenido y tiempo |
| source + session_id | Secuencia de clics | customer_id ficticio opcional permite recurrencia entre sesiones |
| product_id + store_id + ventana | Clics con stock | Requiere tienda conocida en clic |
| store_id + ventana | IoT, clics y stock | Contexto compartido no demuestra causalidad |
| delivery_id / order_id | Seguimiento y futura relación con pedido | No existe todavía enlace directo clic-pedido |
| vehicle_id + ventana | Movilidad entre entregas | Un vehículo puede servir varias entregas |
| source + device_id | Serie por dispositivo | No asumir IDs equivalentes entre fuentes |
| warehouse_id + ventana | Telemetría y sensores de almacén | Contexto común no identifica el mismo activo |
| equipment_id / sensor_id | Sensores de un equipo | Conservar asociación estable |

No se fuerza una relación logística-almacén inexistente en el diseño. Estos
contratos aportan señales para V2/V4, pero no bastan para entrenar modelos sin
históricos/resultados observados ni para calcular ingresos/costo de envío.

## Validación, ejemplos y reproducción

contracts/streaming/validation.py valida sin red los schemas locales, formatos y
la coherencia semántica de stock. JSON Schema estándar no compara dos valores
hermanos: stock_quantity > stock_capacity puede pasar el schema estructural y
debe fallar en validate_event. No se usa una extensión no estándar $data.

La unicidad global, coherencia de secuencias y ausencia efectiva de PII requieren
controles posteriores; no se garantiza que un ID sea ficticio por su patrón.
Todos los ejemplos versionados son ficticios, incluidas coordenadas y clientes.

Ejemplos completos en contracts/streaming/examples/valid/ e invalid/ para los
seis eventos. clic_search demuestra opcionales omitidos; stock_capacity_exceeded
demuestra rechazo semántico aunque la estructura sea válida.

| Ejemplo inválido | Motivo esperado |
|---|---|
| clic_event.json | VIEW_PRODUCT sin product_id |
| iot_event.json | Conteo fraccional |
| stock_event.json | Cantidad negativa |
| location_event.json | Falta compromiso de entrega |
| telemetry_event.json | Unidad incompatible con temperatura |
| warehouse_sensor_event.json | Vibración negativa |
| stock_capacity_exceeded.json | Cantidad mayor que capacidad; fallo semántico |

Los siete ejemplos válidos son los seis eventos completos y clic_search.json,
que omite cliente, producto y tienda cuando no se conocen.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements-dev.txt
python3 -m unittest discover -s contracts/tests -v
python3 -m unittest discover -s infra/tests -v
```

## Escenarios futuros

NORMAL, HIGH_DEMAND, LOW_STOCK, DELIVERY_DELAY, TELEMETRY_ANOMALY y
WAREHOUSE_EQUIPMENT_DEGRADATION se expresarán mediante secuencias de hechos:
frecuencia de interacción/ocupación, stock, compromiso vencido, temperatura y
vibración. No son campos, etiquetas de entrada ni generadores implementados.

## Gobierno y evolución

Cambios de componentes, flujos, contratos o tecnología: registrar decisión →
actualizar Arquitectura de Solución → catálogo/documentación → implementación.
Una modificación del conjunto de campos, enums, métricas o reglas requiere
revisar explícitamente versión y compatibilidad. v1 no acepta extensiones
silenciosas. Los contratos son artefactos locales, no un Schema Registry GCP.

Referencias técnicas: [composición de schemas](https://json-schema.org/understanding-json-schema/reference/object),
[resolución local](https://python-jsonschema.readthedocs.io/en/stable/referencing/) y
[validación y formatos](https://python-jsonschema.readthedocs.io/en/stable/validate/).
