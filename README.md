# RetailSmart

Plataforma de datos retail para decisiones operativas, inventario, informes y
mantenimiento. Arquitectura: fuentes → ingesta → Bronze → Silver → procesamiento
especializado → Gold → consumidores.

| Fase | Estado |
|---|---|
| 2.1 Bootstrap/APIs | COMPLETADO |
| 2.2 IAM | COMPLETADO |
| 2.3 Pub/Sub | COMPLETADO |
| Storage y fases posteriores | PENDIENTE |

Último avance: dos tópicos Pub/Sub y una subscription pull aprovisionados y
validados; segunda ejecución con `changes=0`. Sin pipelines, productores ni cómputo aprovisionado por estas fases.
El Paso 2 integrado continúa en desarrollo.

Comandos (Python 3.10+, gcloud autenticado y `config/dev.env` local):

```bash
python3 -m infra.bootstrap.apis --mode validate
python3 -m infra.iam.manage --mode validate
python3 -m infra.pubsub.manage --mode deploy
python3 -m infra.pubsub.manage --mode validate
python3 -m infra.pubsub.manage --mode destroy  # Previsualización, no elimina
python3 -m unittest discover -s infra/tests -v
```

Configuración: [ejemplo](config/dev.env.example); no versionar `config/dev.env`.
Documentación: [arquitectura](docs/architecture/architecture-overview.md),
[catálogo](docs/standards/resource-catalog.md), [naming](docs/standards/resource-naming.md),
[contratos](docs/data/streaming-contracts.md), [plan](docs/plan/implementation-plan.md).
Evidencias: [2.1](docs/progress/phase-2.1-bootstrap.md),
[2.2](docs/progress/phase-2.2-iam.md), [2.3](docs/progress/phase-2.3-pubsub.md).
[Operación Pub/Sub, destroy/recreate e IAM temporal](infra/pubsub/README.md).

Cada fase cierra con evidencia, pruebas, revisión de secretos, commit y push.
Cómputo futuro solo bajo demanda; cada recurso con costo debe ser eliminable.
