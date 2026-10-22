# RetailSmart — Escenarios sintéticos controlados v1

Diseño aprobado de FASE 3.3, regido por la Arquitectura de Solución. Los perfiles
representan secuencias de hechos de origen. El escenario, sus verticales y su
significado pertenecen al plan/reporte local: nunca al envelope, payload o
atributos Pub/Sub. No cambia ningún contrato ni implementa procesamiento.

## Perfiles y señal de negocio

P=principal; S=secundaria. NORMAL es un **baseline transversal de operación**:
contiene fuentes de V1/V2/V3/V4, sin representar un insight único común.

| Escenario | Eventos | Correlación | Evolución | Verticales | Señal representada |
|---|---|---|---|---|---|
| NORMAL | 18: tres de cada tipo | Entidades estables por fuente | Actividad estable y entrega en compromiso | V1/V2/V3/V4 por presencia de fuentes | Baseline transversal de operación |
| HIGH_DEMAND | 6 clic + 3 IoT + 3 stock | Tienda/producto y tres sesiones | Interés concentrado, ocupación creciente y stock descendente | V1 P/V2 P/V3 P | Presión de demanda |
| LOW_STOCK | 3 stock | Tienda/producto/estantería | 8 → 3 → 0, capacidad 40 | V1 P/V2 P/V3 S | Disponibilidad reducida y quiebre |
| DELIVERY_DELAY | 4 location | Entrega/pedido/vehículo | Detención y confirmación posterior al compromiso | V1 P/V3 P | Retraso/cuello logístico, sin mantenimiento ni falla mecánica |
| TELEMETRY_ANOMALY | 4 telemetry | Cámara/almacén | 4.5 → 4.6 → 9 → 12 CELSIUS | V1 P/V4 P | Desviación térmica observada |
| WAREHOUSE_EQUIPMENT_DEGRADATION | 5 warehouse sensor | Sensor/equipo/almacén | 2.5 → 3.5 → 5 → 7 → 9 MM_S | V1 P/V4 P | Deterioro progresivo de condición |

La capacidad general de location_event en la matriz de fuentes no implica que
DELIVERY_DELAY se asocie a V4: este perfil usa únicamente V1/V3. IoT no incorpora
V4; telemetría y sensores de almacén no incorporan V3. No se producen alertas,
clasificaciones, predicciones ni resultados de modelos.

## Cronología exacta

T0 es start_time. Los desplazamientos son segundos de tiempo de evento, no
intervalos de envío. Los valores canónicos están en
[scenarios.json](../../producers/streaming/scenarios.json).

### NORMAL — 18 eventos

Tres observaciones por tipo en T0, T0+60 y T0+120 segundos. Empates en orden local:
clic, IoT, stock, location, telemetry, warehouse_sensor.

| Evento | +0 s | +60 s | +120 s |
|---|---|---|---|
| clic_event | VIEW_PRODUCT | CLICK | ADD_TO_CART |
| iot_event.value | 12 | 13 | 12 |
| stock_event.stock_quantity | 30 | 29 | 28 |
| location_event | P0, IN_TRANSIT, 4.7 km/h | P1, IN_TRANSIT, 4.7 km/h | P2, DELIVERED, 0 km/h |
| telemetry_event.value | 4.5 | 4.6 | 4.5 |
| warehouse_sensor_event.value | 2.5 | 2.6 | 2.5 |

Una sesión para los tres clics; capacidad 40; dispositivos ACTIVE. Compromiso
logístico constante T0+120. Las mediciones de referencia no certifican salud
operativa ni constituyen thresholds universales.

### HIGH_DEMAND — 12 eventos

- Sesión A: VIEW_PRODUCT +0 s y ADD_TO_CART +10 s.
- Sesión B: VIEW_PRODUCT +20 s y ADD_TO_CART +30 s.
- Sesión C: VIEW_PRODUCT +40 s y ADD_TO_CART +50 s.
- IoT: ocupación 12/24/36 en +0/+60/+120 s; ACTIVE.
- Stock: 30/22/14 en +0/+60/+120 s; capacidad 40.

Misma tienda/producto. Los clics no equivalen a ventas ni demuestran por sí solos
la causa de la reducción de stock. Empates +0 s: clic, IoT y stock.

### LOW_STOCK — 3 eventos

Snapshots de la misma estantería/producto/tienda: 8/3/0 unidades en +0/+60/+120 s,
capacidad constante 40. No se agrega low_stock ni se calcula una alerta.

### DELIVERY_DELAY — 4 eventos

| Offset | Posición | Velocidad km/h | Estado |
|---|---|---:|---|
| +0 s | P0 | 4.7 | IN_TRANSIT |
| +60 s | P1 | 0 | IN_TRANSIT |
| +180 s | P1 | 0 | IN_TRANSIT |
| +240 s | P2 | 0 | DELIVERED |

Compromiso constante T0+120; misma entrega, pedido y vehículo. Se representa una
detención y confirmación 120 segundos después del compromiso. No se inventa un
estado DELAYED, diagnóstico de falla o campo de retraso calculado.

Posiciones sintéticas compartidas con NORMAL:

| Punto | Latitud | Longitud |
|---|---:|---:|
| P0 | -12.0870 | -77.0510 |
| P1 | -12.0865 | -77.0505 |
| P2 | -12.0860 | -77.0500 |

### TELEMETRY_ANOMALY — 4 eventos

Misma cámara/almacén: 4.5/4.6/9.0/12.0 CELSIUS en +0/+60/+120/+180 s,
metric=TEMPERATURE y status=ACTIVE. La desviación es una serie de observaciones;
no se incorpora is_anomaly ni se diagnostica su causa.

### WAREHOUSE_EQUIPMENT_DEGRADATION — 5 eventos

Mismo sensor/equipo/almacén: 2.5/3.5/5.0/7.0/9.0 MM_S en
+0/+60/+120/+180/+240 s, metric=VIBRATION y status=ACTIVE. Incremento progresivo,
sin certificar falla ni calcular un score.

## Contexto e identificadores

Las fábricas existentes aceptan EventContext opcional. Sin contexto, el CLI
unitario conserva UUID/hora real y sus datos anteriores. En modo escenario no se
consulta el reloj ni se generan UUID aleatorios. Las fábricas siguen obteniendo
source/schema_version de los schemas; los ejemplos no son dependencia runtime.

run_id y start_time definen la ejecución lógica. Se normaliza el inicio a UTC;
la identidad determinística considera además perfil, versión y pasos canónicos.
Las entidades usan UUID opacos estables por rol/alias; los dispositivos IoT y las
cámaras tienen roles distintos. Tienda/producto enlazan clics y stock, tienda
incluye IoT, y almacén enlaza contexto de telemetría/sensores sin confundir activos.
Sesiones, entregas y equipos conservan sus claves dentro de cada secuencia.

Cada event_id depende de la ejecución, posición y contenido completo del hecho.
Cambiar un run_id genera nuevas entidades/eventos; repetir exactamente el
contexto reproduce los mismos hechos. Perfiles diferentes se aíslan aunque
compartan run_id. Los nombres de perfiles no aparecen legibles en IDs o eventos.
No se inventa una relación clic-pedido o logística-almacén.

La versión del perfil es metadata de planificación, distinta de schema_version.
Los valores son fijos y externalizados; no hay seed, aleatoriedad ni count.

## Construcción, validación y publicación

1. Resolver configuración local contra catálogo y construir todas las fábricas.
2. Aplicar tiempos, alias y observaciones del perfil mediante contexto.
3. Validar todos los eventos con validate_event, sin duplicar restricciones.
4. Verificar cantidad, cronología, IDs únicos/correlacionados, valores prescritos,
   compromiso constante y ausencia de observaciones posteriores a DELIVERED.
5. Serializar todo el plan como cadenas JSON canónicas inmutables.
6. Dry-run: mostrar plan/eventos/destino y terminar sin GCP.
7. Solo con --publish: comprobar OPERATOR_ACCOUNT y reutilizar el adaptador
   existente, sin cambios IAM y únicamente hacia RS-STR-001.

Un plan inválido bloquea toda publicación, incluso si falla su último evento.
Límite del corte: 18 eventos por perfil. Sin count, rate, alto volumen, retries
propios ni esperas. Orden de invocación local estable, sin garantía de ordering
Pub/Sub. El tiempo de evento es independiente del momento real de envío.

Ante fallo se conservan ACK previos, el elemento fallido se marca ERROR o
UNCERTAIN y los posteriores quedan PENDING. No se republica automáticamente el
plan. Repetir con el mismo contexto conserva event_id, pero no garantiza
exactamente una vez ni consulta mensajes ya publicados.

## Uso y aceptación

Desde la raíz, con dependencias existentes y config/dev.env local:

```bash
python -m producers.streaming.run_scenario --scenario NORMAL --dry-run
python -m producers.streaming.run_scenario --scenario HIGH_DEMAND --dry-run
python -m producers.streaming.run_scenario --scenario LOW_STOCK --dry-run
python -m producers.streaming.run_scenario --scenario DELIVERY_DELAY --dry-run
python -m producers.streaming.run_scenario --scenario TELEMETRY_ANOMALY --dry-run
python -m producers.streaming.run_scenario --scenario WAREHOUSE_EQUIPMENT_DEGRADATION --dry-run
# Contexto reproducible explícito:
python -m producers.streaming.run_scenario --scenario NORMAL --dry-run \
  --run-id acceptance-3.3-001 --start-time 2026-10-21T12:00:00Z
```

Sin flag de modo también es dry-run. Defaults locales versionados: run_id=demo-001,
start_time=2026-10-21T12:00:00Z. Los cambios se realizan con parámetros explícitos,
sin tomar la fecha actual. --publish y --dry-run son excluyentes; publicar exige
run_id/start_time explícitos y OPERATOR_ACCOUNT válido. Un dry-run no exige
cuenta autenticada. El reporte contiene escenario, contexto, eventos, cantidades
y estado por evento; message_id=null y confirmed_count=0 en validación local.

**En FASE 3.3 solo se autoriza validación local. La publicación real de los
escenarios queda pendiente de aprobación tras revisar el resultado.** El
mecanismo de publicación se prueba exclusivamente con transporte simulado.

```bash
python -m unittest discover -s producers/tests -v
python -m unittest discover -s contracts/tests -v
python -m unittest discover -s infra/tests -v
```

Se validan los 46 eventos del conjunto canónico, repetición exacta por contexto,
nueva ejecución por run_id y compatibilidad del CLI unitario. Sin nuevas
librerías, servicios o APIs. Dry-run no genera costo GCP; una futura ejecución
real de los seis perfiles enviaría 46 mensajes pequeños, con retención existente,
sin cómputo ni garantía de gratuidad. No hay consumo ni procesamiento downstream.
