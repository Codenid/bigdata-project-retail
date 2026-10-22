"""Muestras sintéticas unitarias; los contratos oficiales validan el resultado."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import json
from uuid import UUID, uuid4, uuid5

from contracts.streaming.validation import DIRECTORY, validators


def utc_now():
    return datetime.now(timezone.utc)


def timestamp(value):
    return value.isoformat(timespec='microseconds').replace('+00:00', 'Z')


@lru_cache(maxsize=1)
def schema_version():
    common = json.loads((DIRECTORY / 'common-event.schema.json').read_text())
    return common['properties']['schema_version']['const']


@dataclass(frozen=True)
class EventContext:
    """Contexto opcional de origen; no es metadata del contrato publicado."""
    instant: datetime
    namespace: UUID
    event_index: int
    identifiers: dict
    values: dict

    def fact_id(self, body):
        content = json.dumps({'index': self.event_index, 'event': body}, sort_keys=True,
                             ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        return str(uuid5(self.namespace, content))


def _identifier(field, prefix, context):
    return context.identifiers[field] if context else prefix + str(uuid4())


def _envelope(event_type, payload, now=None, context=None):
    schema = validators()[event_type].schema
    if context:
        payload = {key: context.identifiers[key] if key.endswith('_id') else value
                   for key, value in payload.items()}
        payload.update(context.values)
    body = {'event_type': event_type, 'schema_version': schema_version(),
            'event_timestamp': timestamp(context.instant if context else (now or utc_now())),
            'source': schema['properties']['source']['const'], 'payload': payload}
    return {'event_id': context.fact_id(body) if context else str(uuid4()), **body}


def build_clic_event(*, context=None):
    return _envelope('clic_event', {
        'session_id': _identifier('session_id', 'SES-SYN-', context), 'product_id': 'SKU-SYN-0042',
        'action': 'VIEW_PRODUCT', 'channel': 'MOBILE', 'store_id': 'STORE-SYN-001'}, context=context)


def build_iot_event(*, context=None):
    return _envelope('iot_event', {
        'device_id': 'IOT-SYN-001', 'store_id': 'STORE-SYN-001',
        'metric': 'OCCUPANCY', 'value': 12, 'unit': 'COUNT', 'status': 'ACTIVE'}, context=context)


def build_stock_event(*, context=None):
    return _envelope('stock_event', {
        'store_id': 'STORE-SYN-001', 'product_id': 'SKU-SYN-0042',
        'shelf_id': 'SHELF-SYN-001', 'stock_quantity': 12, 'stock_capacity': 40}, context=context)


def build_location_event(*, context=None):
    now = context.instant if context else utc_now()
    return _envelope('location_event', {
        'delivery_id': _identifier('delivery_id', 'DEL-SYN-', context),
        'order_id': _identifier('order_id', 'ORD-SYN-', context),
        'vehicle_id': 'VEH-SYN-001', 'latitude': -12.087, 'longitude': -77.051,
        'delivery_status': 'IN_TRANSIT', 'speed_kmh': 18.5,
        'expected_delivery_timestamp': timestamp(now + timedelta(hours=1))}, now, context=context)


def build_telemetry_event(*, context=None):
    return _envelope('telemetry_event', {
        'device_id': 'FRIDGE-SYN-001', 'warehouse_id': 'WH-SYN-001',
        'metric': 'TEMPERATURE', 'value': 4.5, 'unit': 'CELSIUS', 'status': 'ACTIVE'}, context=context)


def build_warehouse_sensor_event(*, context=None):
    return _envelope('warehouse_sensor_event', {
        'sensor_id': 'WS-SYN-001', 'equipment_id': 'EQUIP-SYN-001',
        'warehouse_id': 'WH-SYN-001', 'metric': 'VIBRATION', 'value': 2.5,
        'unit': 'MM_S', 'status': 'ACTIVE'}, context=context)


def build_event(event_type, *, context=None):
    # Despacho de fábricas, no definición de enums ni validación del contrato.
    factories = {factory.__name__.removeprefix('build_'): factory for factory in (
        build_clic_event, build_iot_event, build_stock_event, build_location_event,
        build_telemetry_event, build_warehouse_sensor_event)}
    factory = factories.get(event_type)
    if factory is None:
        raise ValueError('Fábrica no disponible para el tipo solicitado')
    return factory(context=context)
