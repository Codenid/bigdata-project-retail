# RetailSmart Source Emulator — V1 Streaming

Aplicación local que emula aplicaciones/dispositivos de origen. No consume,
confirma subscriptions, transforma eventos ni implementa Batch/Dataflow.

```bash
python -m pip install -r apps/requirements.txt
streamlit run apps/source_emulator.py
```

Abre http://127.0.0.1:8501. Usa config/dev.env existente y OPERATOR_ACCOUNT activo
en gcloud. Pulsa **Conectar OPERATOR_ACCOUNT**: comprueba identidad, rechaza
impersonación/overrides y obtiene un token solo en memoria. No cambia IAM.
Si falta pubsub.topics.publish sobre RS-STR-001, detén y solicita autorización;
no asigna permisos. Nunca hay publicación al abrir una página o conectar.

## Operación

1. Selecciona Streaming y Operación libre.
2. En Estantería Inteligente elige 1 evt/s y START. Observa métricas/actividad.
3. Cambia Rate (1, 2, 5, 10 o Custom) y pulsa STOP para detener esa fuente.
4. Activa Tracking Logístico / Repartidores de la misma forma.
5. STOP ALL antes de cambiar a TELEMETRY_ANOMALY. Solo Cámaras Frigoríficas
   queda habilitada; START reproduce cuatro muestras y se detiene al terminar.
6. Activity muestra las últimas 50 publicaciones y permite inspeccionar JSON.

Overview resume todas las fuentes. Batch muestra exclusivamente Coming next.
SEND ONCE valida/publica un evento de una fuente detenida y respeta su rate.
START ALL inicia solo fuentes compatibles; STOP ALL detiene todas. No se
pueden mezclar perfiles activos o editar escenario mientras hay fuentes activas.
Una ejecución nueva de escenario produce otros IDs, preservando correlaciones
entre fuentes del mismo plan. No se añaden scenario/vertical/insights al evento.

Los perfiles son los seis existentes, sin duplicar sus valores o contratos.
Se prevalidan íntegros. Sus timestamps siguen el reloj sintético original (por
eso pueden adelantarse al reloj de publicación); Rate controla la velocidad
real de emisión. No se reescriben compromisos ni hechos para acelerar un perfil.
Modo libre usa las fábricas existentes con UUID nuevos y muestras independientes.

## Límites y cierre

Configuración externa opcional en config/dev.env o variables de entorno:

| Variable | Predeterminado | Límite |
|---|---:|---|
| EMULATOR_MAX_RATE | 20 | 0.1–20 evt/s por fuente |
| EMULATOR_MAX_RUN_SECONDS | 300 | >0 y ≤300 por START |
| EMULATOR_LEASE_SECONDS | 5 | >0 y ≤10 |

Rate es un objetivo/máximo, no una promesa de throughput; la latencia puede
reducirlo. No hay cola acumulativa ni ráfagas de recuperación. Cada fuente tiene
un worker serial con Event de parada. Fallo de validación/publicación detiene
esa fuente y no reintenta ni reenvía una publicación incierta. La UI muestra
ERROR sin exponer excepciones que puedan contener datos sensibles.

STOP espera el envío en curso (timeout HTTP 5s, join 6s), luego no salen nuevos
mensajes. Si no termina, se informa y se bloquea un nuevo START sobre ese worker.
Desconectar y detener cierra el engine. Cerrar una pestaña deja de renovar el
heartbeat: los productores paran al expirar el lease, más el envío en curso.
No se promete detección instantánea del cierre del navegador. El proceso
registra además cierre atexit; los workers son rastreables y de vida acotada.
El token vence localmente a los 40 minutos y requiere reconectar; no se refresca
ni cambia autenticación automáticamente. No se muestran tokens, credenciales,
ackId ni parámetros de autenticación en métricas o actividad.

El límite por fuente aplica a una sesión local; se recomienda una sesión
operativa. La app solo escucha en loopback. Los eventos son sintéticos. El
costo proviene de bytes publicados en Pub/Sub, sin nueva infraestructura o
cómputo GCP permanente. STOP/desconectar y la ventana máxima limitan emisiones.
Eliminar mensajes ya publicados no forma parte de esta herramienta.

## Engine y pruebas

producers/emulator/engine.py no importa Streamlit. Exponer start_source,
stop_source, send_once, start_all, stop_all, set_rate, set_scenario, heartbeat,
snapshot y close permite reutilizarlo desde otras interfaces. sources.py separa
catálogo/presentación de transporte y permite incorporar fuentes Batch en otra
versión, sin generar Batch en V1. publish mantiene gcloud por defecto; el engine
inyecta OperatorPublisher REST, conservando la comprobación de message_id.

```bash
python -m unittest discover -s producers/emulator/tests -v
python scripts/demo_source_emulator.py  # Solo muestra el plan, sin GCP
# Solo con autorización de publicación: genera otra demo; no repetir la evidencia.
python scripts/demo_source_emulator.py --publish --report /tmp/nueva-demo.json
```

La demo real usa el mismo engine de la UI: estantería y tracking a 1 evt/s, cinco
segundos cada uno; después las cuatro muestras del perfil térmico. El reporte
exclusivo impide sobrescribir una demo y conserva event_id/message_id/JSON. Los
botones y navegación se prueban con AppTest y transporte simulado; la demo real
no pretende ser una prueba de clicks en un navegador. No hace pull ni ACK.

[Evidencia de V1](../docs/progress/source-emulator-v1.md).
