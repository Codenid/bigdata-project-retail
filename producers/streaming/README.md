# Productor CLI unitario — FASE 3.2

Herramienta manual del diseño aprobado de la Arquitectura de Solución. Construye
un hecho ficticio, reutiliza el contrato oficial y publica un solo mensaje en
RS-STR-001. No crea infraestructura, modifica IAM ni consume mensajes.

## Preparación

Python 3.10+, gcloud instalado para publicación y config/dev.env configurado según
config/dev.env.example. Para dependencias Python:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

Configurar OPERATOR_ACCOUNT explícitamente en el env local ignorado. Identifica
la cuenta activa que ejecuta herramientas operativas/pruebas. BOOTSTRAP_ACCOUNT
es de aprovisionamiento/administración: ambos valores pueden coincidir, pero no
hay fallback ni sustitución runtime. No versionar correos reales o credenciales.
No se crean claves ni Service Accounts.

## Uso

Desde la raíz del repositorio:

```bash
python -m producers.streaming.send_event --type clic_event
python -m producers.streaming.send_event --type iot_event
python -m producers.streaming.send_event --type stock_event
python -m producers.streaming.send_event --type location_event
python -m producers.streaming.send_event --type telemetry_event
python -m producers.streaming.send_event --type warehouse_sensor_event
# Construcción y validación local, sin gcloud/autenticación/red:
python -m producers.streaming.send_event --type stock_event --dry-run
# Configuración alternativa, siempre contrastada con Resource Catalog:
python -m producers.streaming.send_event --type stock_event --dry-run --config config/dev.env
```

No hay --count, rate, escenarios, generación masiva ni parámetro de tópico libre.
El destino deriva del proyecto configurado y RS-STR-001 del catálogo. Un tópico
no catalogado en configuración se rechaza antes de contactar GCP.

## Construcción y contrato

build_event.py contiene las seis fábricas build_<tipo>(). Construyen muestras
propias, sin leer ejemplos/fixtures. UUID nuevo por hecho y sesión/entrega nueva
cuando corresponde; producto/tienda y almacén ficticios compartidos permiten
correlación entre fuentes. Las mediciones son muestras fijas, no escenarios.
Cada entrega nueva tiene un compromiso sintético una hora después de su
observación; nunca se desplaza el compromiso de una entrega preexistente.

source y schema_version se leen de los schemas. Las fábricas no definen enums,
restricciones ni validadores. Los valores literales son datos de muestra, no
reglas del contrato. contracts/streaming/validation.py sigue siendo la autoridad:
un cambio incompatible detendrá el productor antes de publicar.

Flujo: configuración → construcción → validate_event → serialización estricta
→ cuenta operativa → publish → message_id. El publicador recibe exactamente la
cadena serializada tras validar, sin reconstruir el hecho. Dry-run termina tras
mostrar evento/destino; puede ejecutarse sin OPERATOR_ACCOUNT autenticado.

## Autenticación y mínimo privilegio

El adaptador operativo consulta gcloud auth list sin --account para no ocultar
una discrepancia de cuenta activa. Exige coincidencia con OPERATOR_ACCOUNT y
rechaza overrides de credenciales/impersonación. Publica seleccionando después
--account explícito. No cambia cuenta activa, credenciales ni configuración SDK.
No utiliza el wrapper de bootstrap, que selecciona una identidad administrativa.

Pub/Sub verifica pubsub.topics.publish al recibir el publish. Si lo deniega,
se detiene y reporta el requisito; no se modifican permisos. Un eventual grant
se aprobaría por separado, con roles/pubsub.publisher únicamente en RS-STR-001.
No se usa RS-SEC-001, RS-SEC-002 ni el binding Editor preexistente del deployer.

## Resultado y errores

Stdout contiene un resultado JSON: result OK/ERROR, event_type, event_id, topic,
message_id, timestamp, event_timestamp, mode, published y publication_uncertain.
Incluye el evento válido para inspección y, ante error, stage/error cuando hay
contexto disponible. Argumentos inválidos salen con código 2 antes de operar;
fallos de ejecución con 1; éxito con 0. Stderr de gcloud permanece visible.

Dry-run: mode=DRY_RUN, published=false, message_id=null. Publicación: OK solo tras
obtener exactamente un message_id válido. timestamp es hora UTC local del
resultado, no publishTime de servidor. Un ACK no certifica procesamiento downstream.

No hay bucles de reintento propios. Timeout, respuesta sin ID o fallo de
transporte pueden dejar publicación incierta: no reenviar automáticamente.
Pub/Sub/CLI no ofrecen aquí garantía exactamente una vez. Cada invocación nueva
construye un hecho con otro ID, no un reintento del evento previo.

## Pruebas y costo

```bash
python -m unittest discover -s producers/tests -v
python -m unittest discover -s contracts/tests -v
python -m unittest discover -s infra/tests -v
```

Pruebas locales usan transporte simulado, sin GCP. La aceptación real aprobada
es una publicación por tipo, seis mensajes, tras seis dry-runs. No se consumen
mensajes ni se agrega una subscription para comprobarlos.

Dry-run no genera operaciones GCP. Publicación unitaria pequeña tiene costo
esperado bajo, sin garantía de gratuidad; se conserva retención de una hora de
la subscription existente. Sin consumidor, los mensajes pueden expirar. No hay
cómputo, APIs nuevas ni procesamiento Bronze/Silver/Gold en esta fase.

Referencias: [publicación gcloud](https://docs.cloud.google.com/sdk/gcloud/reference/pubsub/topics/publish),
[cuenta activa](https://docs.cloud.google.com/sdk/gcloud/reference/auth/list),
[IAM Pub/Sub](https://docs.cloud.google.com/pubsub/docs/access-control).


## Escenarios controlados — FASE 3.3

Las fábricas incorporan un contexto opcional determinístico; el CLI unitario y
sus defaults permanecen iguales. El nuevo CLI run_scenario es dry-run por defecto:

```bash
python -m producers.streaming.run_scenario --scenario NORMAL --dry-run
```

Los seis perfiles contienen 18/12/3/4/4/5 eventos (46 canónicos), sin seed, count o
rate. Se valida el plan completo antes de cualquier publicación explícita y se
reutilizan validate_event y publish.py. Los nombres de escenarios no van en
mensajes ni atributos. Publicación real de escenarios pendiente de aprobación;
aceptación actual exclusivamente local. Detalle en
[escenarios sintéticos](../../docs/data/synthetic-scenarios.md).
