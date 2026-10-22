"""Contratos aprobados: estructura, semántica, ejemplos y referencias locales."""
from copy import deepcopy
import json
import socket
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator, ValidationError
from contracts.streaming.validation import DIRECTORY, validate_event, validators

EVENTS = ('clic_event', 'iot_event', 'stock_event', 'location_event',
          'telemetry_event', 'warehouse_sensor_event')


def example(name):
    return json.loads((DIRECTORY / 'examples/valid' / (name + '.json')).read_text())


class StreamingContracts(unittest.TestCase):
    def rejects(self, event):
        with self.assertRaises(ValidationError):
            validate_event(event)

    def test_all_seven_schemas_valid_and_exact_inventory(self):
        paths = list(DIRECTORY.glob('*.schema.json'))
        self.assertEqual({p.stem for p in paths}, {e + '.schema' for e in EVENTS} | {'common-event.schema'})
        for path in paths:
            with self.subTest(path=path.name):
                Draft202012Validator.check_schema(json.loads(path.read_text()))
        self.assertEqual(set(validators()), set(EVENTS))

    def test_valid_examples_for_every_event_and_search(self):
        files = list((DIRECTORY / 'examples/valid').glob('*.json'))
        self.assertEqual(len(files), 7)
        for path in files:
            with self.subTest(path=path.name):
                validate_event(json.loads(path.read_text()))

    def test_valid_examples_have_distinct_fact_identifiers(self):
        events = [json.loads(path.read_text()) for path in (DIRECTORY / 'examples/valid').glob('*.json')]
        self.assertEqual(len({event['event_id'] for event in events}), len(events))

    def test_invalid_examples_rejected_for_every_event(self):
        files = list((DIRECTORY / 'examples/invalid').glob('*.json'))
        self.assertEqual(len(files), 7)
        for path in files:
            with self.subTest(path=path.name):
                self.rejects(json.loads(path.read_text()))

    def test_references_and_validation_are_offline(self):
        validators.cache_clear()
        with patch.object(socket, 'socket', side_effect=AssertionError('network forbidden')):
            for event in EVENTS:
                validate_event(example(event))

    def test_every_envelope_field_required(self):
        for event_type in EVENTS:
            original = example(event_type)
            for key in original:
                with self.subTest(event=event_type, missing=key):
                    event = deepcopy(original)
                    del event[key]
                    self.rejects(event)

    def test_required_payload_fields(self):
        for event_type in EVENTS:
            schema = json.loads((DIRECTORY / (event_type + '.schema.json')).read_text())
            for key in schema['properties']['payload']['required']:
                with self.subTest(event=event_type, missing=key):
                    event = example(event_type)
                    del event['payload'][key]
                    self.rejects(event)

    def test_null_rejected_in_every_declared_field(self):
        for event_type in EVENTS:
            original = example(event_type)
            for section in ('envelope', 'payload'):
                keys = original if section == 'envelope' else original['payload']
                for key in keys:
                    with self.subTest(event=event_type, section=section, key=key):
                        event = deepcopy(original)
                        target = event if section == 'envelope' else event['payload']
                        target[key] = None
                        self.rejects(event)

    def test_additional_fields_and_derived_results_rejected(self):
        for event_type in EVENTS:
            for key in ('scenario', 'vertical', 'KPI', 'insights', 'is_anomaly', 'model_result', 'unexpected'):
                for section in ('envelope', 'payload'):
                    with self.subTest(event=event_type, field=key, section=section):
                        event = example(event_type)
                        (event if section == 'envelope' else event['payload'])[key] = 'not an observed field'
                        self.rejects(event)

    def test_event_type_and_source_pair_are_fixed(self):
        for event_type in EVENTS:
            event = example(event_type)
            event['source'] = 'unapproved_source'
            self.rejects(event)
            # El schema específico también rechaza otro evento, aunque su envelope sea válido.
            event = example(event_type)
            event['event_type'] = EVENTS[(EVENTS.index(event_type) + 1) % len(EVENTS)]
            with self.assertRaises(ValidationError):
                validators()[event_type].validate(event)

    def test_unknown_names_and_schema_versions(self):
        for name in ('click_event', 'insight_event', 'unknown', '', 12):
            event = example('clic_event')
            event['event_type'] = name
            self.rejects(event)
        for version in ('2.0', '1', 1.0):
            event = example('stock_event')
            event['schema_version'] = version
            self.rejects(event)

    def test_real_calendar_and_utc_profile(self):
        for key in ('event_timestamp', 'expected_delivery_timestamp'):
            for value in ('2026-02-30T12:00:00Z', '2026-02-29T12:00:00Z',
                          '2026-10-21', '2026-10-21T12:00:00+00:00',
                          '2026-10-21T12:00:00-05:00', '2026-10-21T25:00:00Z',
                          '2026-10-21T12:00:60Z', '2026-10-21T12:00:00Z\n'):
                with self.subTest(key=key, value=value):
                    event = example('location_event')
                    (event if key == 'event_timestamp' else event['payload'])[key] = value
                    self.rejects(event)
            event = example('location_event')
            (event if key == 'event_timestamp' else event['payload'])[key] = '2024-02-29T12:00:00.125Z'
            validate_event(event)

    def test_empty_or_whitespace_identifiers_rejected(self):
        for value in ('', ' ', 'id with spaces', 'id\n', '\tid'):
            for key in ('event_id', 'session_id'):
                event = example('clic_event')
                (event if key == 'event_id' else event['payload'])[key] = value
                self.rejects(event)

    def test_click_product_conditional_and_optionals(self):
        event = example('clic_search')
        self.assertNotIn('customer_id', event['payload'])
        self.assertNotIn('store_id', event['payload'])
        for action in ('CLICK', 'VIEW_PRODUCT', 'ADD_TO_CART'):
            event['payload']['action'] = action
            self.rejects(event)
            event['payload']['product_id'] = 'SKU-0042'
            validate_event(event)
            del event['payload']['product_id']
        event['payload']['action'] = 'SEARCH'
        validate_event(event)

    def test_action_channel_status_and_delivery_enums(self):
        for event_type, field, value in [('clic_event','action','PURCHASE'), ('clic_event','channel','EMAIL'),
                                        ('iot_event','status','UNKNOWN'), ('telemetry_event','status','FAILED'),
                                        ('warehouse_sensor_event','status','FAILED'),
                                        ('location_event','delivery_status','DELAYED')]:
            event = example(event_type)
            event['payload'][field] = value
            self.rejects(event)
        for event_type in ('iot_event', 'telemetry_event', 'warehouse_sensor_event'):
            event = example(event_type)
            event['payload']['status'] = 'INACTIVE'
            validate_event(event)

    def test_metric_unit_pairs_are_exact(self):
        for event_type in ('iot_event', 'telemetry_event', 'warehouse_sensor_event'):
            for field in ('metric','unit'):
                event = example(event_type)
                event['payload'][field] = 'OTHER'
                self.rejects(event)

    def test_numeric_types_not_strings_or_booleans(self):
        fields = {'iot_event': ['value'], 'stock_event': ['stock_quantity','stock_capacity'],
                  'location_event': ['latitude','longitude','speed_kmh'],
                  'telemetry_event': ['value'], 'warehouse_sensor_event': ['value']}
        for event_type, keys in fields.items():
            for key in keys:
                for value in ('42', True):
                    with self.subTest(event=event_type, key=key, value=value):
                        event = example(event_type)
                        event['payload'][key] = value
                        self.rejects(event)

    def test_stock_semantics_separate_from_standard_schema(self):
        event = json.loads((DIRECTORY / 'examples/invalid/stock_capacity_exceeded.json').read_text())
        validators()['stock_event'].validate(event)  # Estructura estándar válida.
        self.rejects(event)  # Coherencia del hecho inválida.
        for quantity, capacity in ((0,1), (30,30)):
            event['payload'].update(stock_quantity=quantity, stock_capacity=capacity)
            validate_event(event)
        for quantity, capacity in ((-1,30), (0,0), (1.5,30), (1,2.5)):
            event['payload'].update(stock_quantity=quantity, stock_capacity=capacity)
            self.rejects(event)

    def test_observed_anomalies_and_past_commitments_remain_valid(self):
        for value in (-25.5, 75.0):
            event = example('telemetry_event')
            event['payload']['value'] = value
            validate_event(event)
        event = example('warehouse_sensor_event')
        event['payload']['value'] = 1000
        validate_event(event)
        event = example('location_event')
        event['payload']['delivery_status'] = 'DELIVERED'
        event['event_timestamp'] = '2026-10-21T15:00:00Z'
        validate_event(event)  # Compromiso 13:00 vencido: hecho válido.

    def test_geographic_and_nonnegative_boundaries(self):
        for field, valid, invalid in [('latitude',[-90,90],[-90.1,90.1]),
                                      ('longitude',[-180,180],[-180.1,180.1]),
                                      ('speed_kmh',[0,120],[-0.1])]:
            for value in valid:
                event = example('location_event'); event['payload'][field] = value
                validate_event(event)
            for value in invalid:
                event = example('location_event'); event['payload'][field] = value
                self.rejects(event)
        for event_type in ('iot_event', 'warehouse_sensor_event'):
            event = example(event_type); event['payload']['value'] = 0
            validate_event(event)
            event['payload']['value'] = -1
            self.rejects(event)

    def test_non_json_and_nonfinite_values_rejected(self):
        for value in (float('nan'), float('inf'), float('-inf')):
            event = example('telemetry_event'); event['payload']['value'] = value
            self.rejects(event)
        for event in ([], None, 'text', {'event_type': []}):
            self.rejects(event)
