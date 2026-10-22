"""Planes sintéticos pequeños y determinísticos; sin acceso a GCP."""
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from contracts.streaming.validation import utc_timestamp, validate_event, validators
from producers.streaming.build_event import EventContext, build_event, timestamp

PROFILES_PATH = Path(__file__).with_name('scenarios.json')
MAX_EVENTS = 18  # Límite del corte aprobado; no es un parámetro de volumen.


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def definitions():
    return json.loads(PROFILES_PATH.read_text())


def parse_start_time(value):
    if not isinstance(value, str) or not utc_timestamp(value):
        raise ValueError('start_time debe ser una fecha/hora UTC válida terminada en Z')
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


@dataclass
class ScenarioPlan:
    scenario: str
    run_id: str
    start_time: datetime
    version: str
    profile: dict
    namespace: UUID
    events: list

    @property
    def counts(self):
        return dict(sorted(Counter(event['event_type'] for event in self.events).items()))


def check_steps(profile):
    steps = profile['steps']
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_EVENTS:
        raise ValueError('El perfil debe contener entre 1 y 18 eventos; no admite alto volumen')
    previous = -1
    for row in steps:
        if not isinstance(row, dict) or set(row) - {
                'event_type', 'offset_seconds', 'values', 'entities', 'commitment_offset_seconds'}:
            raise ValueError('Estructura de paso no reconocida')
        event_type, offset = row['event_type'], row['offset_seconds']
        if event_type not in validators():
            raise ValueError('Tipo de evento no oficial en el perfil')
        if type(offset) is not int or offset < 0 or offset < previous:
            raise ValueError('Offsets deben ser enteros no negativos en orden temporal')
        previous = offset
        values, entities = row['values'], row.get('entities', {})
        if not isinstance(values, dict) or not isinstance(entities, dict):
            raise ValueError('values/entities deben ser objetos de planificación')
        if any(key.endswith('_id') or key == 'expected_delivery_timestamp' for key in values):
            raise ValueError('Identificadores y compromiso se resuelven mediante contexto, no values')
        properties = validators()[event_type].schema['properties']['payload']['properties']
        for key, alias in entities.items():
            if key not in properties or not key.endswith('_id') or not isinstance(alias, str) or not alias.strip():
                raise ValueError('Alias de entidad no reconocido')
        commitment = row.get('commitment_offset_seconds')
        if event_type == 'location_event':
            if type(commitment) is not int or commitment < 0:
                raise ValueError('Location requiere compromiso relativo no negativo')
        elif commitment is not None:
            raise ValueError('Compromiso relativo solo corresponde a location_event')


def context_for(plan, index, row):
    properties = validators()[row['event_type']].schema['properties']['payload']['properties']
    identifiers = {key: str(uuid5(plan.namespace, canonical(
        {'field': key, 'entity': row.get('entities', {}).get(key, key)})))
        for key in properties if key.endswith('_id')}
    values = deepcopy(row['values'])
    try:
        instant = plan.start_time + timedelta(seconds=row['offset_seconds'])
        if row['event_type'] == 'location_event':
            values['expected_delivery_timestamp'] = timestamp(
                plan.start_time + timedelta(seconds=row['commitment_offset_seconds']))
    except OverflowError as error:
        raise ValueError('Cronología fuera del calendario admitido') from error
    return EventContext(instant, plan.namespace, index, identifiers, values)


def build_plan(scenario, run_id=None, start_time=None):
    data = definitions()
    if scenario not in data['profiles']:
        raise ValueError('Escenario no aprobado')
    run_id = data['defaults']['run_id'] if run_id is None else run_id
    if not isinstance(run_id, str) or not run_id or any(char.isspace() for char in run_id):
        raise ValueError('run_id debe ser no vacío y sin espacios')
    instant = parse_start_time(data['defaults']['start_time'] if start_time is None else start_time)
    profile = deepcopy(data['profiles'][scenario])
    check_steps(profile)
    namespace = uuid5(NAMESPACE_URL, canonical({'scenario': scenario, 'run_id': run_id,
        'start_time': timestamp(instant), 'version': data['version'], 'steps': profile['steps']}))
    plan = ScenarioPlan(scenario, run_id, instant, data['version'], profile, namespace, [])
    for index, row in enumerate(profile['steps']):
        plan.events.append(build_event(row['event_type'], context=context_for(plan, index, row)))
    return plan


def validate_plan(plan):
    """Validar todos los hechos y relaciones antes de cualquier autenticación/envío."""
    check_steps(plan.profile)
    if len(plan.events) != len(plan.profile['steps']):
        raise ValueError('Cantidad de eventos distinta del plan')
    seen_ids, deliveries = set(), {}
    names = tuple(definitions()['profiles'])
    for index, (event, row) in enumerate(zip(plan.events, plan.profile['steps'])):
        validate_event(event)
        if event['event_id'] in seen_ids:
            raise ValueError('event_id duplicado dentro del plan')
        seen_ids.add(event['event_id'])
        context = context_for(plan, index, row)
        if event['event_type'] != row['event_type'] or event['event_timestamp'] != timestamp(context.instant):
            raise ValueError('Tipo o cronología del evento difiere del plan')
        payload = event['payload']
        if any(payload[key] != value for key, value in context.identifiers.items() if key in payload):
            raise ValueError('Correlación de identificadores inconsistente')
        if any(payload.get(key) != value for key, value in context.values.items()):
            raise ValueError('Observaciones distintas a los valores del perfil')
        body = {key: value for key, value in event.items() if key != 'event_id'}
        if event['event_id'] != context.fact_id(body):
            raise ValueError('event_id no corresponde al contenido y posición del hecho')
        if any(name.casefold() in canonical(event).casefold() for name in names):
            raise ValueError('Nombre de escenario encontrado dentro del evento')
        if event['event_type'] == 'location_event':
            key = payload['delivery_id']
            relation = (payload['order_id'], payload['vehicle_id'], payload['expected_delivery_timestamp'])
            if key in deliveries:
                previous, delivered = deliveries[key]
                if previous != relation:
                    raise ValueError('Pedido, vehículo o compromiso cambió para la misma entrega')
                if delivered:
                    raise ValueError('Una entrega confirmada no admite observaciones posteriores en estos perfiles')
            deliveries[key] = (relation, payload['delivery_status'] == 'DELIVERED')


def serialize_plan(plan):
    validate_plan(plan)
    # Las cadenas son inmutables; el publicador no reconstruye ni altera los hechos.
    return tuple(canonical(event) for event in plan.events)
