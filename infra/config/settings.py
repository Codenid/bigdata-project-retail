"""Configuración externa contrastada con el catálogo, sin ejecutar archivos env."""
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESOURCE_KEYS = (
    'EVENTS_TOPIC_ID', 'EVENTS_SUBSCRIPTION_ID', 'INSIGHTS_TOPIC_ID',
    'BRONZE_BUCKET', 'SILVER_BUCKET', 'DATAFLOW_BUCKET', 'GOLD_DATASET_ID',
    'DATAFLOW_SERVICE_ACCOUNT_ID', 'DEPLOYER_SERVICE_ACCOUNT_ID',
)


def load(path):
    values = {}
    for number, raw in enumerate(Path(path).read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep or not re.fullmatch(r'[A-Z][A-Z0-9_]*', key) or key in values:
            raise ValueError(f'Configuración inválida en línea {number}')
        values[key] = value.strip()
    for key in values:
        values[key] = os.environ.get(key, values[key])
    if values.get('PROJECT_ID'):
        if values.get('GCP_PROJECT_ID') and values['PROJECT_ID'] != values['GCP_PROJECT_ID']:
            raise ValueError('PROJECT_ID y GCP_PROJECT_ID no coinciden')
        values['GCP_PROJECT_ID'] = values['PROJECT_ID']
    required = ('GCP_PROJECT_ID', 'GCP_REGION', 'GCP_LOCATION', 'RESOURCE_SUFFIX',
                'ENVIRONMENT', 'BOOTSTRAP_ACCOUNT', *RESOURCE_KEYS,
                'ACK_DEADLINE_SECONDS', 'MESSAGE_RETENTION_SECONDS',
                'SUBSCRIPTION_EXPIRATION')
    for key in required:
        if not values.get(key):
            raise ValueError(f'Falta configurar {key}')
    if not re.fullmatch(r'[a-z][a-z0-9-]{4,28}[a-z0-9]', values['GCP_PROJECT_ID']):
        raise ValueError('GCP_PROJECT_ID inválido')
    for key in ('GCP_REGION', 'GCP_LOCATION'):
        if not re.fullmatch(r'[a-z]+-[a-z]+[0-9]+', values[key]):
            raise ValueError(f'{key} debe ser regional según catálogo')
    if values['GCP_REGION'] != values['GCP_LOCATION']:
        raise ValueError('Este corte requiere GCP_REGION = GCP_LOCATION')
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', values['RESOURCE_SUFFIX']):
        raise ValueError('RESOURCE_SUFFIX inválido')
    catalog = (ROOT / 'docs/standards/resource-catalog.md').read_text()
    rows = [[c.strip() for c in line.split('|')[1:-1]]
            for line in catalog.splitlines()
            if line.startswith('| RS-') and '| approved |' in line]
    if len(rows) != len(RESOURCE_KEYS):
        raise ValueError('El catálogo aprobado cambió; revisar mapping de configuración')
    component_ids = ('RS-STR-001', 'RS-STR-002', 'RS-STR-003',
                     'RS-DATA-001', 'RS-DATA-002', 'RS-STR-004',
                     'RS-DATA-003', 'RS-SEC-001', 'RS-SEC-002')
    by_id = {row[0]: row for row in rows}
    if set(by_id) != set(component_ids):
        raise ValueError('Component IDs del catálogo no coinciden con este corte')
    resources = {}
    for key, component_id in zip(RESOURCE_KEYS, component_ids):
        row = by_id[component_id]
        expected = row[7].replace('<suffix>', values['RESOURCE_SUFFIX'])
        actual = values[key].replace('<suffix>', values['RESOURCE_SUFFIX'])
        if actual != expected or values['ENVIRONMENT'] != row[6]:
            raise ValueError(f'{key} no coincide con catálogo: {row[0]}')
        if row[5] == 'Bucket' and len(actual) > 63:
            raise ValueError(f'{key} excede longitud permitida')
        values[key] = actual
        labels = dict(project='retailsmart', environment=row[6],
                      domain=row[2].lower(), managed_by=row[14],
                      component_id=row[0].lower(), data_classification=row[12])
        for column, label in ((10, 'role'), (11, 'layer')):
            if row[column] != 'n/a':
                labels[label] = row[column]
        if row[3] != 'Transversal':
            labels['vertical'] = 'multi' if '/' in row[3] else row[3].lower()
        resources[row[0]] = dict(name=actual, scope=row[8], location=row[9], labels=labels)
    if not 10 <= int(values['ACK_DEADLINE_SECONDS']) <= 600:
        raise ValueError('ACK_DEADLINE_SECONDS fuera de rango')
    retention = int(values['MESSAGE_RETENTION_SECONDS'])
    if not 600 <= retention <= 2678400:
        raise ValueError('MESSAGE_RETENTION_SECONDS fuera de rango')
    expiration = values['SUBSCRIPTION_EXPIRATION']
    if expiration != 'never' and (int(expiration) < 86400 or int(expiration) <= retention):
        raise ValueError('SUBSCRIPTION_EXPIRATION insuficiente')
    if 'RETAIN_ACKED_MESSAGES' in values and values['RETAIN_ACKED_MESSAGES'] != 'false':
        raise ValueError('RETAIN_ACKED_MESSAGES debe ser false en fase 2.3')
    if 'SUBSCRIPTION_RETRY_POLICY' in values and values['SUBSCRIPTION_RETRY_POLICY'] != 'immediate':
        raise ValueError('Solo retry immediate está aprobado en fase 2.3')
    return values, resources
