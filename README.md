# RetailSmart

Plataforma de datos retail para decisiones operativas, inventario, informes y
mantenimiento. Arquitectura: fuentes → ingesta → Bronze → Silver → procesamiento
especializado → Gold → consumidores.

| Fase | Estado |
|---|---|
| 2.1 Bootstrap/APIs | COMPLETADO |
| 2.2 IAM | COMPLETADO |
| 2.3 Pub/Sub | COMPLETADO |
| 2.4 Storage | COMPLETADO |
| 2.5 BigQuery | COMPLETADO |
| 2.6 Deploy integrado | COMPLETADO |
| Fases posteriores | PENDIENTE |

Último avance: orquestación secuencial del Streaming Core existente, con
validación integrada, IAM temporal y destroy protegido por preview. Conserva
identidades y APIs; segundo deploy con `changes=0` y ciclos IAM separados.
Se conserva un binding Pub/Sub Editor preexistente; detalle en la evidencia 2.6.

Comandos (Python 3.10+, gcloud autenticado y `config/dev.env` local):

```bash
./scripts/deploy_streaming_core.sh
./scripts/validate_streaming_core.sh
./scripts/destroy_streaming_core.sh  # Preview; puede usar IAM temporal
# Eliminación explícita, únicamente con dataset y buckets vacíos:
./scripts/destroy_streaming_core.sh --execute-destroy
python3 -m unittest discover -s infra/tests -v
```

Configuración: [ejemplo](config/dev.env.example); no versionar `config/dev.env`.
Documentación: [arquitectura](docs/architecture/architecture-overview.md),
[catálogo](docs/standards/resource-catalog.md), [naming](docs/standards/resource-naming.md),
[contratos](docs/data/streaming-contracts.md), [plan](docs/plan/implementation-plan.md).
Evidencias: [2.1](docs/progress/phase-2.1-bootstrap.md),
[2.2](docs/progress/phase-2.2-iam.md), [2.3](docs/progress/phase-2.3-pubsub.md),
[2.4](docs/progress/phase-2.4-storage.md), [2.5](docs/progress/phase-2.5-bigquery.md),
[2.6](docs/progress/phase-2.6-integrated-deploy.md).
Operación y eliminación: [Pub/Sub](infra/pubsub/README.md),
[Storage y costo residual de Bronze](infra/storage/README.md),
[BigQuery e IAM temporal](infra/bigquery/README.md).

Cada fase cierra con evidencia, pruebas, revisión de secretos, commit y push.
Cómputo futuro solo bajo demanda; cada recurso con costo debe ser eliminable.
