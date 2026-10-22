# Recepción controlada del Streaming Core

Inspección puntual de RS-STR-002, resuelta desde configuración/catálogo. No crea
recursos, cambia IAM, publica eventos ni implementa procesamiento downstream.
Requiere Python 3.10+, requirements-dev.txt, gcloud y OPERATOR_ACCOUNT activo.
No utiliza BOOTSTRAP_ACCOUNT ni RS-SEC-001 para recepción.

```bash
# Inspección predeterminada, sin ACK; un único pull de hasta 10 mensajes:
python -m consumers.streaming.pull_events
# Contrastar hasta 46 entregas contra la evidencia histórica, sin ACK:
python -m consumers.streaming.pull_events --limit 46 --verify-phase33
# Consolidación local de reportes JSON previamente guardados; sin GCP:
python -m consumers.streaming.verify_phase33 reporte-1.json reporte-2.json
python -m unittest discover -s consumers/tests -v
```

`--limit` admite 1–50. No existe selector de subscription. Se carga
config/dev.env (o --config), se comprueba OPERATOR_ACCOUNT mediante el guard
existente, se obtiene un token operativo solo en memoria y se consulta
`testIamPermissions` para `pubsub.subscriptions.consume`. Esta comprobación es
informativa: la autorización definitiva la aplica Pub/Sub al efectuar pull.
El rol previsto es roles/pubsub.subscriber sobre RS-STR-002; si falta acceso,
la ejecución se detiene. La herramienta nunca asigna IAM ni cambia credenciales.

## Inspección y ACK

Sin `--ack` es inspección. El pull puede mantener temporalmente las entregas
pendientes de ACK hasta el deadline existente de 60 segundos; después pueden
volver a entregarse. No es un dry-run sin acceso a GCP.

`--ack` requiere `--verify-phase33`; usarlo solo con aprobación operativa
expresa. En el cierre inicial de Fase 3.4 **no se autoriza ACK real**.
Solo se seleccionan entregas con JSON/contrato válidos y coincidencia de event_id,
message_id, tipo, timestamp, versión y hash canónico de la evidencia Fase 3.3.
Un evento válido ajeno permanece VALID / NOT_ACKED. Inválidos permanecen INVALID.
No se envían atributos ni se modifica el evento.

Se valida todo el lote antes de seleccionar ACK. Conflictos de event_id o
message_id excluyen todas las entregas relacionadas del lote. No existe estado
persistente entre procesos; la consolidación offline identifica conflictos
entre reportes y no autoriza ACK. Un ACK aceptado se registra ACKED; un error o
timeout deja NOT_ACKED con ack_uncertain=true. No se garantiza ausencia de
redelivery, incluso después de un ACK aceptado.

## Verificación histórica

El manifiesto versionado consumers/tests/fixtures/phase33-expected.json se usa
también durante ejecución con --verify-phase33. No constituye otro contrato.
Contiene los 46 IDs de publicación y contextos documentados en Fase 3.3; los
hashes se reconstruyeron offline usando sus perfiles y fábricas existentes,
sin publicar y sin depender de /tmp. Las pruebas comprueban su reconstrucción
y correspondencia con la evidencia versionada. El consumidor en runtime no
importa fábricas ni escenarios.

SHA-256 se calcula sobre JSON canónico: claves ordenadas, separadores compactos,
UTF-8, ensure_ascii=false, valores finitos. Compara contenido, no espacios ni
orden de claves. La metadata de escenario pertenece solo al manifiesto local.

| Evento | Esperados |
|---|---:|
| clic_event | 9 |
| iot_event | 6 |
| stock_event | 9 |
| location_event | 7 |
| telemetry_event | 7 |
| warehouse_sensor_event | 8 |
| Total | 46 |

COMPLETE significa 46 esperados únicos, válidos y coincidentes; PARTIAL indica
entre 1 y 45; UNAVAILABLE indica cero. Estos estados describen únicamente la
evidencia recuperada. PARTIAL/UNAVAILABLE no provocan código de error por sí
solos. Un pull puede devolver menos mensajes que el límite o estar vacío sin
demostrar expiración ni ausencia de backlog. La retención aprobada es 3600
segundos desde publicación; los eventos históricos podrían no estar disponibles.
No se republican eventos ni se modifica retención para obtener aceptación.

Cada reporte JSON muestra message_id, event_id, event_type, event_timestamp,
schema_version, validation, ack_status y clasificación histórica. Incluye
conteos de válidos/ inválidos, duplicados, conflictos, ajenos y cobertura.
La cobertura cuenta eventos únicos; las entregas duplicadas se reportan aparte.
Los IDs faltantes permiten comparar reportes sin asumir ordering global.
No muestra token, ackId, atributos o payload. La consolidación offline utiliza
reportes locales de confianza; sus hashes no son una firma de autenticidad.

Fallos de configuración, identidad, acceso, transporte, inválidos o conflictos
producen código distinto de cero. Los errores se sanean para no exponer datos.
Sin retries propios, loops de recepción, auto-ACK, NACK, workers, cambios del
ack deadline, nuevos recursos o dependencias. El token se obtiene de gcloud;
REST unary se ejecuta con biblioteca estándar y sin redirecciones HTTP.
Costo limitado a solicitudes puntuales de Pub/Sub; sin cómputo permanente.

Referencias: [pull](https://docs.cloud.google.com/pubsub/docs/reference/rest/v1/projects.subscriptions/pull),
[ACK](https://docs.cloud.google.com/pubsub/docs/reference/rest/v1/projects.subscriptions/acknowledge),
[comprobación informativa de permisos](https://docs.cloud.google.com/pubsub/docs/reference/rest/v1/projects.subscriptions/testIamPermissions).
