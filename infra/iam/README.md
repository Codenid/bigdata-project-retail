# FASE 2.2 — Identidades Streaming Core

Solo gestiona RS-SEC-001 y RS-SEC-002 del catálogo. Nombres y proyecto se cargan
desde config/dev.env; roles y metadatos desde infra/config/iam.json. No habilita
APIs ni crea recursos de datos o cómputo. No crea claves ni roles personalizados.
Estas identidades no reservan cómputo; impersonar no inicia workers ni jobs.

## Bindings aprobados

- BOOTSTRAP_ACCOUNT recibe roles/iam.serviceAccountTokenCreator únicamente sobre
  RS-SEC-002: permite impersonación sin claves.
- RS-SEC-002 recibe roles/iam.serviceAccountViewer sobre RS-SEC-001 y RS-SEC-002:
  permite describir cada identidad y leer su política IAM.
- RS-SEC-001 no recibe roles runtime en 2.2.

Antes de cualquier mutación, se consulta la definición real de Viewer y se
comprueba iam.serviceAccounts.get e iam.serviceAccounts.getIamPolicy. La consulta
real del 2026-10-21 confirmó ambos. El rol contiene además lectura de metadatos
de claves; el script no invoca esas operaciones ni lista claves.

Las Service Accounts no admiten labels convencionales. El displayName contiene
Component ID y propósito; description conserva los labels derivados del catálogo
como metadata JSON. Scope global y location n/a se mantienen en catálogo.

## Ejecución

```bash
python3 -m infra.iam.manage --mode deploy
python3 -m infra.iam.manage --mode validate
python3 -m infra.iam.manage --mode deploy
python3 -m unittest discover -s infra/tests -v
```

Deploy lista cuentas y consulta políticas antes de crear o actualizar. Solo
agrega bindings faltantes; no reemplaza políticas completas ni elimina bindings
ajenos. Validate no muta: usa impersonación del deployer para describir las dos
cuentas y consultar sus políticas. La segunda ejecución espera changes=0.
Errores de lectura o permisos no se interpretan como ausencia de recursos.
Si hay propagación IAM pendiente, se informa el error y se puede reejecutar;
los cambios ya aplicados se conservan sin duplicación.

La identidad bootstrap debe disponer previamente de permisos para listar/crear
cuentas, leer/modificar sus políticas, consultar roles y leer la política IAM
del proyecto. No se le conceden permisos automáticamente. Se rechazan roles
amplios configurados sobre las cuentas y asignaciones directas a las identidades
en el proyecto. Esto no certifica ausencia de permisos heredados o por grupos;
si no se puede leer la política del proyecto, la validación falla.

Para la futura ejecución Dataflow, el principal que lance el job podría requerir
roles/iam.serviceAccountUser sobre RS-SEC-001. Esa asignación y los roles de
Dataflow, Pub/Sub, Storage y BigQuery quedan diferidos a sus fases.

Eliminación/recreación: el destroy integrado del Paso 2 deberá retirar únicamente
los tres bindings gestionados y eliminar estas dos cuentas mediante bootstrap,
con el deployer al final y previa comprobación de dependencias. No se implementa
ni ejecuta destroy en esta fase para evitar borrar las identidades validadas.

Referencia de lectura y scope de cuentas:
https://docs.cloud.google.com/iam/docs/service-account-permissions

## Evidencia — 2026-10-21

Se crearon las dos cuentas y los tres bindings anteriores en GCP. La validación
completa terminó con código 0 usando impersonación del deployer para get y
getIamPolicy de ambas cuentas. Repetir deploy terminó con applied_changes=0,
changes=0 y código 0. Las 16 pruebas locales de fases 2.1/2.2 pasaron.

Incidencias resueltas sin ampliar permisos:
- Consulta de rol predefinido con --project: se corrigió el runner compartido
  para omitir ese flag exclusivamente al consultar roles predefinidos globales.
- getAccessToken denegado inmediatamente después del binding: tras confirmar
  la política exacta y reintentar, la impersonación funcionó. La validación y
  repetición finales pasaron sin modificar roles (propagación IAM).

No se habilitaron APIs adicionales ni se crearon recursos de datos o cómputo.
La ausencia comprobada de roles amplios se limita a bindings directos observados;
no se certifican permisos heredados de organizaciones, carpetas o grupos.
