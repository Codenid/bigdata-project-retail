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
| 2.6 Integración y fases posteriores | PENDIENTE |

Último avance: dataset Gold vacío en us-central1, sin expiraciones predeterminadas
ni modelo de almacenamiento explícito; segundo deploy con `changes=0`.
IAM temporal retirado al finalizar, sin
permisos runtime nuevos, cargas, jobs ni capacidad dedicada.
El Paso 2 integrado continúa en desarrollo.

Comandos (Python 3.10+, gcloud autenticado y `config/dev.env` local):

```bash
python3 -m infra.bootstrap.apis --mode validate
python3 -m infra.iam.manage --mode validate
python3 -m infra.pubsub.manage --mode deploy
python3 -m infra.pubsub.manage --mode validate
python3 -m infra.pubsub.manage --mode destroy  # Previsualización, no elimina
python3 -m infra.storage.manage --mode deploy
python3 -m infra.storage.manage --mode validate
python3 -m infra.bigquery.manage --mode deploy
python3 -m infra.bigquery.manage --mode validate
python3 -m unittest discover -s infra/tests -v
```

Configuración: [ejemplo](config/dev.env.example); no versionar `config/dev.env`.
Documentación: [arquitectura](docs/architecture/architecture-overview.md),
[catálogo](docs/standards/resource-catalog.md), [naming](docs/standards/resource-naming.md),
[contratos](docs/data/streaming-contracts.md), [plan](docs/plan/implementation-plan.md).
Evidencias: [2.1](docs/progress/phase-2.1-bootstrap.md),
[2.2](docs/progress/phase-2.2-iam.md), [2.3](docs/progress/phase-2.3-pubsub.md),
[2.4](docs/progress/phase-2.4-storage.md), [2.5](docs/progress/phase-2.5-bigquery.md).
Operación y eliminación: [Pub/Sub](infra/pubsub/README.md),
[Storage y costo residual de Bronze](infra/storage/README.md),
[BigQuery e IAM temporal](infra/bigquery/README.md).

Cada fase cierra con evidencia, pruebas, revisión de secretos, commit y push.
Cómputo futuro solo bajo demanda; cada recurso con costo debe ser eliminable.
