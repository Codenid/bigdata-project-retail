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
| 3.1 Event Contracts | COMPLETADO |
| 3.2 Productor CLI unitario | COMPLETADO |
| 3.3 Escenarios controlados (validación local) | COMPLETADO |
| Publicación real de escenarios | COMPLETADO: 46/46 ACK |
| 3.4 Recepción Pub/Sub | IMPLEMENTADO; prueba fresca PARTIAL 4/6; ACK 0 |
| Fases posteriores | PENDIENTE |

Último avance: seis eventos frescos publicados, cuatro únicos recibidos y válidos;
ACKED=0 porque faltan dos por comprobar. Cierre funcional pendiente de autorizar
inspecciones adicionales. Las 195 pruebas pasan; sin cambios de infraestructura o IAM.

Comandos: Python 3.10+; para infraestructura, gcloud autenticado y
`config/dev.env` local. Los tests de contratos no requieren GCP.

```bash
./scripts/deploy_streaming_core.sh
./scripts/validate_streaming_core.sh
./scripts/destroy_streaming_core.sh  # Preview; puede usar IAM temporal
# Eliminación explícita, únicamente con dataset y buckets vacíos:
./scripts/destroy_streaming_core.sh --execute-destroy
python3 -m pip install -r requirements-dev.txt
python -m producers.streaming.send_event --type stock_event --dry-run
python -m producers.streaming.run_scenario --scenario NORMAL --dry-run
python -m consumers.streaming.pull_events --limit 46 --verify-phase33  # Sin ACK
python3 -m unittest discover -s consumers/tests -v
python3 -m unittest discover -s producers/tests -v
python3 -m unittest discover -s contracts/tests -v
python3 -m unittest discover -s infra/tests -v
```

Configuración: [ejemplo](config/dev.env.example); no versionar `config/dev.env`.
Documentación: [arquitectura](docs/architecture/architecture-overview.md),
[catálogo](docs/standards/resource-catalog.md), [naming](docs/standards/resource-naming.md),
[contratos](docs/data/streaming-contracts.md), [plan](docs/plan/implementation-plan.md).
Evidencias: [2.1](docs/progress/phase-2.1-bootstrap.md),
[2.2](docs/progress/phase-2.2-iam.md), [2.3](docs/progress/phase-2.3-pubsub.md),
[2.4](docs/progress/phase-2.4-storage.md), [2.5](docs/progress/phase-2.5-bigquery.md),
[2.6](docs/progress/phase-2.6-integrated-deploy.md),
[3.1](docs/progress/phase-3.1-event-contracts.md),
[3.2](docs/progress/phase-3.2-unit-producer.md),
[3.3](docs/progress/phase-3.3-controlled-scenarios.md),
[3.4](docs/progress/phase-3.4-pubsub-reception.md).
Productor: [uso e identidad operativa](producers/streaming/README.md).
Recepción: [inspección y ACK protegido](consumers/streaming/README.md).
Escenarios: [perfiles, cronología y reproducción](docs/data/synthetic-scenarios.md).
Operación y eliminación: [Pub/Sub](infra/pubsub/README.md),
[Storage y costo residual de Bronze](infra/storage/README.md),
[BigQuery e IAM temporal](infra/bigquery/README.md).

Cada fase cierra con evidencia, pruebas, revisión de secretos, commit y push.
Cómputo futuro solo bajo demanda; cada recurso con costo debe ser eliminable.
