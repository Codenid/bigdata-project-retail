# RetailSmart

Plataforma de datos retail para respaldar decisiones operativas e inventario.

Estado:
- 2.1 Bootstrap/APIs ✅
- 2.2 IAM ✅
- 2.3 Pub/Sub ⏳

Implementado: validación de configuración y bootstrap de APIs en GCP; gestión y
validación idempotente de identidades y permisos IAM mínimos.

Validación (Python 3.10+):

```bash
python3 -m infra.bootstrap.apis --mode validate
python3 -m infra.iam.manage --mode validate
python3 -m unittest discover -s infra/tests -v
```

Documentación detallada: [arquitectura](docs/architecture/architecture-overview.md),
[fase 2.1](docs/progress/phase-2.1-bootstrap.md) y
[fase 2.2](docs/progress/phase-2.2-iam.md).
