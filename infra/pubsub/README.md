# FASE 2.3 — Pub/Sub Streaming Core

Aprovisiona únicamente RS-STR-001 (Eventos), RS-STR-002 (pull de Eventos) y
RS-STR-003 (Insights). Los nombres y labels se contrastan con el catálogo.
Scope global, location n/a. No se configura Message Storage Policy ni existen
variables de residencia en este corte: GCP aplica sus defaults/políticas heredadas.

## Operación

Requisitos: fases 2.1/2.2 completas, gcloud autenticado y config/dev.env local.
No sobrescribir un env ya configurado con el ejemplo. El bootstrap necesita
leer servicios/roles/política del proyecto y aplicar el binding aprobado.
El script no le concede estos permisos ni habilita APIs adicionales.

```bash
python3 -m infra.pubsub.manage --mode deploy
python3 -m infra.pubsub.manage --mode validate
python3 -m infra.pubsub.manage --mode deploy
python3 -m unittest discover -s infra/tests -v
```

Deploy crea solo lo ausente y actualiza labels/propiedades si difieren. La
segunda ejecución debe devolver changes=0. Los errores se propagan: si IAM aún
no se propagó, reejecutar sin añadir roles. Validate no modifica recursos Pub/Sub y exige la
configuración aprobada; puede conceder y retirar IAM temporal para inspección; no publica, consume ni confirma mensajes.

Propiedades externas en config/dev.env.example: ack 60 s, retención 3600 s,
retain acked false, expiración 604800 s y retry immediate (ausencia de retryPolicy).
Los límites numéricos se validan antes de llamar a GCP. No se habilitan ordering,
exactly-once, DLQ, filtros, push, exportación, schemas, snapshots ni retención de
tópico. Features ajenas detectadas en recursos existentes provocan error, no se
eliminan silenciosamente. Una asociación incorrecta o recurso sin marca de
pertenencia bloquea deploy. No se adoptan tópicos de terceros por nombre.

La retención de una hora puede descartar eventos no consumidos. Revisar antes
del E2E; la expiración elimina la subscription tras siete días inactiva y deploy
la recrea. No hay validación E2E en esta fase.

## IAM y costo

infra/config/pubsub.json define el rol y las operaciones requeridas. El bootstrap
aplica roles/pubsub.editor al deployer a nivel proyecto y el script opera Pub/Sub
mediante impersonación. Este permiso temporal es más amplio que mínimo estricto:
permite gestionar otros recursos y publicar/consumir aunque el script no lo haga.
Debe revisarse posteriormente. Desde 2.6, deploy/validate/destroy añaden el binding
solo si falta y lo retiran en finally, confirmando la limpieza. Los bindings
preexistentes, incluidos los heredados de ejecuciones anteriores, se conservan;
se informa preexisting_binding=true y no se presume su procedencia.
changes cuenta recursos; iam_changes cuenta altas/bajas temporales por separado.
No ejecutar operaciones concurrentes sobre el mismo binding. SIGKILL o caída del
host puede impedir finally; un fallo de cleanup se reporta como error.
RS-SEC-001 no recibe permisos runtime. Se conservan
los bindings de 2.2 y no se conceden roles Owner/Editor básicos ni IAM Admin.

Los recursos vacíos sin tráfico tienen costo esperado prácticamente nulo. Tráfico,
backlog y transferencias futuros pueden generar cargos; la retención no limita
el gasto monetario. No se reserva cómputo. No se detectan ni sustituyen de forma
silenciosa restricciones de Free Trial: cualquier error se muestra y detiene el
script. Precios: https://cloud.google.com/pubsub/pricing

## Destroy y recreación

```bash
# Previsualización: sin borrar recursos; puede usar IAM temporal:
python3 -m infra.pubsub.manage --mode destroy
# Elimina la subscription y luego ambos tópicos, perdiendo mensajes pendientes:
python3 -m infra.pubsub.manage --mode destroy --execute-destroy
# Recrear:
python3 -m infra.pubsub.manage --mode deploy
```

Destroy verifica labels de pertenencia y rechaza subscriptions adicionales,
incluso conectadas desde otro proyecto. Tolera recursos ausentes. El binding
creado por la operación se retira siempre; los preexistentes se conservan.
Las comprobaciones previas no bloquean cambios concurrentes externos;
ejecutar con productores/despliegues detenidos. No elimina cuentas, otros recursos
ni APIs. No se ofrece purge de proyecto ni búsqueda por prefijos.

Referencias de CLI:
- https://docs.cloud.google.com/sdk/gcloud/reference/pubsub/topics/create
- https://docs.cloud.google.com/sdk/gcloud/reference/pubsub/subscriptions/create
- https://docs.cloud.google.com/sdk/gcloud/reference/pubsub/subscriptions/update
