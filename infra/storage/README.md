# FASE 2.4 — Storage Streaming Core

Aprovisiona solo RS-DATA-001 (Bronze), RS-DATA-002 (Silver) y RS-STR-004
(Dataflow Staging/Temp). Catálogo y config/dev.env determinan los nombres con
RESOURCE_SUFFIX, proyecto y región. No crea jobs, objetos, carpetas ni otros
recursos. Requiere fases 2.1/2.2 completas y Storage API ya habilitada.

## Políticas

| Propiedad | Bronze | Silver | Técnico |
|---|---|---|---|
| Clase / location | STANDARD / us-central1 | STANDARD / us-central1 | STANDARD / us-central1 |
| Acceso uniforme | enabled | enabled | enabled |
| Prevención pública | enforced | enforced | enforced |
| Soft delete | 604800 s (7 días) | 0 (disabled) | 0 (disabled) |
| Lifecycle | Sin reglas | Sin reglas | Una regla Delete, age=1 |
| Versioning / Bucket Lock | Sin configurar | Sin configurar | Sin configurar |

Cifrado Google-managed, sin CMEK, retention policy, Autoclass ni replicación
adicional. No se añaden ACL de objetos. La regla técnica es asíncrona: los
objetos se vuelven elegibles por edad, no se garantiza borrado exactamente al
cumplir 24 horas. Revisar esta política antes de ejecuciones Dataflow prolongadas.
Silver y técnico no recuperan objetos borrados; Bronze conserva recuperación.

## Configuración y operación

Config externa: config/dev.env.example y infra/config/storage.json. El módulo
central carga nombres/labels contrastados con catálogo; el módulo Storage valida
las propiedades de esta fase antes de llamar a GCP. No sustituir un env local
existente con el ejemplo. No versionar config/dev.env.

```bash
python3 -m infra.storage.manage --mode deploy
python3 -m infra.storage.manage --mode validate
python3 -m infra.storage.manage --mode deploy
python3 -m unittest discover -s infra/tests -v
```

Python usa gcloud para IAM y autenticación; la JSON API oficial de Storage permite
crear cada bucket con labels y protecciones en una sola petición atómica. Esto
evita buckets sin marcas de pertenencia si se interrumpe un paso posterior.
El token de impersonación vive solo en memoria; no se imprime ni guarda.

Deploy crea lo ausente o actualiza configuración mutable con precondición de
metageneración. No interpreta errores de permisos como ausencia. Un nombre global
ocupado detiene la creación sin generar sufijos nuevos. Proyecto, location,
labels de pertenencia y features fuera de alcance se revisan antes de mutar.
No se adoptan buckets ajenos ni se desactiva un bloqueo/retención existente.

Validate solo lee datos de Storage. Puede gestionar temporalmente IAM como se
explica abajo; no sube ni borra objetos. Comprueba metadata, cifrado por defecto,
soft delete, lifecycle, labels, protecciones, ausencia de bindings públicos y
permisos Storage directos del runtime. No certifica todos los accesos heredados
por grupos, organización o carpeta. La comparación se realiza sobre metadata
actual de la API, sin confundir campos adicionales del servidor con drift.

## IAM temporal e idempotencia

El bootstrap debe disponer previamente de permisos para leer servicios, roles,
proyecto y política IAM, y añadir/retirar el binding aprobado. No se le asignan
permisos automáticamente. RS-SEC-002 usa roles/storage.admin a nivel proyecto:
es más amplio que mínimo estricto y debe revisarse posteriormente.

Flujo: comprobar política inicial → añadir binding si falta → impersonar deployer
→ operar → finally retirar solo el binding creado → confirmar política. Si la
operación falla o se interrumpe normalmente, se intenta cleanup; un fallo de
cleanup se reporta explícitamente. Una terminación forzada (SIGKILL/caída del
host) puede impedir finally: revisar la política antes de reintentar. No ejecutar
operaciones concurrentes sobre este binding; no se puede atribuir un grant externo
concurrente idéntico. Un binding preexistente nunca se elimina automáticamente.

La propagación IAM puede provocar 403 transitorio: la lectura inicial reintenta
con límites externos y avisos visibles. Otros errores fallan y activan cleanup.
Si persiste el 403 no se amplían roles; revisar el error y reejecutar.

`changes` cuenta cambios de buckets. El segundo deploy debe mostrar changes=0.
`iam_changes` cuenta por separado grant/revoke (normalmente 2 por operación).
La idempotencia preserva el estado final, no evita el acceso temporal necesario.
`temporary_binding_removed=true` confirma que se retiró el grant creado; si era
preexistente, preexisting_binding=true y no se modifica. RS-SEC-001 no recibe
roles Storage. Se conservan los demás bindings y recursos de fases anteriores.

## Destroy/recreate y costos

```bash
# Previsualización de buckets; puede asignar/retirar IAM temporal:
python3 -m infra.storage.manage --mode destroy
# Eliminar buckets vacíos:
python3 -m infra.storage.manage --mode destroy --execute-destroy
# Purga explícita de datos y eliminación de estos buckets:
python3 -m infra.storage.manage --mode destroy --execute-destroy --purge
# Recrear conforme al catálogo:
python3 -m infra.storage.manage --mode deploy
```

Se comprueba pertenencia y que todos los buckets estén vacíos antes de eliminar
el primero, salvo --purge. La purga elimina generaciones identificadas, sin
comodines o prefijos de otros buckets. Se toleran buckets ausentes, no errores
de acceso. No elimina IAM de terceros, identidades ni APIs. Puede haber cambios
concurrentes entre preflight y delete: ejecutar con writers detenidos.

**Bronze mantiene soft delete incluso durante destroy.** Sus datos borrados pueden
seguir retenidos y generar cargos durante siete días. No se fuerza su eliminación
permanente ni se desactiva esa protección. La disponibilidad de un nombre para
recreación y una eventual recuperación de bucket dependen de las reglas de GCP;
si hay conflicto se reporta, no se renombra. La validación habitual no ejecuta
purga ni destroy destructivo en GCP.

Los buckets vacíos no reservan cómputo. Datos, operaciones, recuperación y
transferencias futuros pueden tener costo. Standard regional en us-central1 es
compatible con Free Tier sujeto a límites compartidos de la cuenta; no hay
presupuesto duro por bucket. Mantener datos pequeños y revisar uso. Cualquier
restricción Free Trial/organización se reporta sin sustitución de arquitectura.

Referencias:
- https://docs.cloud.google.com/storage/docs/json_api/v1/buckets/insert
- https://docs.cloud.google.com/storage/docs/soft-delete
- https://docs.cloud.google.com/storage/docs/lifecycle
- https://cloud.google.com/storage/pricing
