# RetailSmart

Plataforma de datos retail para decisiones en tiempo real, planificación de
inventario, informes operativos y mantenimiento proactivo.

Arquitectura resumida: fuentes → ingesta streaming/batch → Bronze → Silver →
procesamiento especializado → Gold → consumidores. La implementación actual
se limita a la infraestructura base del Streaming Core en GCP.

| Fase | Estado |
|---|---|
| 2.1 Bootstrap/APIs | COMPLETADO |
| 2.2 IAM | COMPLETADO |
| 2.3 Pub/Sub | PENDIENTE |

Último avance: dos identidades IAM validadas mediante impersonación, tres
bindings aprobados y reejecución sin cambios. No hay pipelines ni cómputo activo
aprovisionado por estas fases. El Paso 2 completo continúa en desarrollo.

Comandos principales (Python 3.10+, gcloud autenticado y configuración local):

```bash
cp config/dev.env.example config/dev.env  # Solo al configurar por primera vez
# Completar los valores locales; no versionar config/dev.env.
python3 -m infra.bootstrap.apis --mode config
python3 -m infra.bootstrap.apis --mode validate
python3 -m infra.iam.manage --mode validate
python3 -m unittest discover -s infra/tests -v
```

Documentación: [arquitectura](docs/architecture/architecture-overview.md),
[mapping](docs/architecture/implementation-mapping.md),
[contratos](docs/data/streaming-contracts.md),
[fuentes y verticales](docs/data/source-to-vertical-matrix.md),
[plan](docs/plan/implementation-plan.md),
[naming](docs/standards/resource-naming.md) y
[catálogo](docs/standards/resource-catalog.md).

Operación y evidencia: [bootstrap](infra/bootstrap/README.md),
[IAM](infra/iam/README.md), [fase 2.1](docs/progress/phase-2.1-bootstrap.md) y
[fase 2.2](docs/progress/phase-2.2-iam.md).
Cada fase cierra con README, evidencia, pruebas, revisión de Git/secretos, commit
y push al branch actual; un fallo de push se reporta sin cambiar credenciales.
Los componentes con costo se ejecutarán bajo demanda y deberán tener eliminación
reproducible; no se han implementado aún los comandos integrados deploy/destroy.
