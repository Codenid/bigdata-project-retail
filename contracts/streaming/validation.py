"""Validación local de contratos v1; sin productor, CLI ni acceso a GCP."""
from datetime import datetime
from functools import lru_cache
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from referencing import Registry, Resource

DIRECTORY = Path(__file__).resolve().parent


def utc_timestamp(value):
    """Comprobar calendario real; el schema restringe el perfil UTC a Z."""
    if not isinstance(value, str):
        return True  # El tipo se comprueba mediante JSON Schema.
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return value.endswith('Z') and parsed.utcoffset().total_seconds() == 0
    except (ValueError, AttributeError, OverflowError):
        return False


@lru_cache(maxsize=1)
def validators():
    schemas = [json.loads(path.read_text()) for path in sorted(DIRECTORY.glob('*.schema.json'))]
    for schema in schemas:
        Draft202012Validator.check_schema(schema)
    # Registro en memoria: nunca descarga contratos ni resuelve referencias por red.
    registry = Registry().with_resources((schema['$id'], Resource.from_contents(schema)) for schema in schemas)
    checker = FormatChecker()
    checker.checks('date-time')(utc_timestamp)
    return {schema['properties']['event_type']['const']: Draft202012Validator(
        schema, registry=registry, format_checker=checker) for schema in schemas
        if schema['properties'].get('event_type', {}).get('const')}


def validate_event(event):
    """Validar estructura y coherencia del hecho; no calcula insights/thresholds."""
    try:
        json.dumps(event, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValidationError('El evento debe contener valores JSON finitos') from error
    if not isinstance(event, dict) or not isinstance(event.get('event_type'), str):
        raise ValidationError('event_type es requerido en un objeto JSON')
    validator = validators().get(event['event_type'])
    if validator is None:
        raise ValidationError('event_type no oficial')
    validator.validate(event)
    if event['event_type'] == 'stock_event':
        payload = event['payload']
        if payload['stock_quantity'] > payload['stock_capacity']:
            raise ValidationError('stock_quantity supera stock_capacity', path=['payload', 'stock_quantity'])
