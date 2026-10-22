"""Perfiles aprobados: reproducibilidad, correlación, prevalidación y envío simulado."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from datetime import timedelta
import io
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from jsonschema import ValidationError
from contracts.streaming.validation import validate_event, validators
from infra.config.settings import ROOT
from producers.streaming import build_event as builder
from producers.streaming import publish as transport
from producers.streaming import scenarios
from producers.streaming.run_scenario import main
from producers.streaming.send_event import main as unit_main

EXPECTED_COUNTS = {'NORMAL':18, 'HIGH_DEMAND':12, 'LOW_STOCK':3, 'DELIVERY_DELAY':4,
                   'TELEMETRY_ANOMALY':4, 'WAREHOUSE_EQUIPMENT_DEGRADATION':5}
START = '2026-10-21T12:00:00Z'


class ControlledScenarios(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'test.env'
        text = (ROOT / 'config/dev.env.example').read_text()
        for key, value in {'GCP_PROJECT_ID':'retailsmart-test', 'GCP_REGION':'us-central1',
                           'GCP_LOCATION':'us-central1', 'RESOURCE_SUFFIX':'test',
                           'BOOTSTRAP_ACCOUNT':'bootstrap@example.com',
                           'OPERATOR_ACCOUNT':'operator@example.com'}.items():
            text = text.replace(key + '=\n', key + '=' + value + '\n')
        self.path.write_text(text)
        self.out, self.err = io.StringIO(), io.StringIO()

    def plan(self, name='NORMAL', run_id='test-001'):
        return scenarios.build_plan(name, run_id, START)

    def cli(self, *args):
        with redirect_stdout(self.out), redirect_stderr(self.err):
            status = main(['--config', str(self.path), *args])
        return status, json.loads(self.out.getvalue().splitlines()[-1])

    def publish_args(self, name='LOW_STOCK'):
        return ['--scenario',name,'--publish','--run-id','test-001','--start-time',START]

    def events(self, plan, event_type):
        return [event for event in plan.events if event['event_type'] == event_type]

    def test_all_six_profiles_exact_counts_and_46_valid_events(self):
        self.assertEqual(set(scenarios.definitions()['profiles']), set(EXPECTED_COUNTS))
        total = 0
        for name, count in EXPECTED_COUNTS.items():
            with self.subTest(name=name):
                plan = self.plan(name)
                messages = scenarios.serialize_plan(plan)
                self.assertEqual(len(messages), count)
                self.assertEqual(sum(plan.counts.values()), count)
                for message in messages:
                    validate_event(json.loads(message))
                total += count
        self.assertEqual(total, 46)

    def test_same_scenario_run_id_start_time_same_serialized_bytes(self):
        for name in EXPECTED_COUNTS:
            with self.subTest(name=name):
                self.assertEqual(scenarios.serialize_plan(self.plan(name)),
                                 scenarios.serialize_plan(self.plan(name)))

    def test_different_run_id_new_logical_execution(self):
        for name in EXPECTED_COUNTS:
            with self.subTest(name=name):
                first, second = self.plan(name, 'run-a'), self.plan(name, 'run-b')
                self.assertNotEqual(scenarios.serialize_plan(first), scenarios.serialize_plan(second))
                self.assertFalse({e['event_id'] for e in first.events} & {e['event_id'] for e in second.events})
                ids = lambda plan: {value for event in plan.events for key,value in event['payload'].items() if key.endswith('_id')}
                self.assertFalse(ids(first) & ids(second))

    def test_changed_content_does_not_reuse_fact_ids(self):
        first = self.plan('LOW_STOCK')
        definitions = scenarios.definitions()
        definitions['profiles']['LOW_STOCK']['steps'][0]['values']['stock_quantity'] = 9
        with patch.object(scenarios, 'definitions', return_value=definitions):
            second = self.plan('LOW_STOCK')
        self.assertNotEqual(first.events[0]['event_id'], second.events[0]['event_id'])

    def test_no_clock_random_uuid_or_network_in_scenario_construction(self):
        with patch.object(builder, 'utc_now', side_effect=AssertionError('clock forbidden')), \
             patch.object(builder, 'uuid4', side_effect=AssertionError('random UUID forbidden')), \
             patch.object(socket, 'socket', side_effect=AssertionError('network forbidden')):
            for name in EXPECTED_COUNTS:
                scenarios.serialize_plan(self.plan(name))

    def test_event_ids_unique_across_profiles_and_within_each(self):
        ids = [e['event_id'] for name in EXPECTED_COUNTS for e in self.plan(name).events]
        self.assertEqual(len(ids), len(set(ids)))

    def test_no_event_contains_any_scenario_name_or_metadata(self):
        for name in EXPECTED_COUNTS:
            for event in self.plan(name).events:
                encoded = scenarios.canonical(event).casefold()
                self.assertTrue(all(label.casefold() not in encoded for label in EXPECTED_COUNTS))
                for fields in (event, event['payload']):
                    self.assertNotIn('scenario', fields)
                    self.assertNotIn('vertical', fields)
                    self.assertNotIn('run_id', fields)
                    self.assertNotIn('start_time', fields)

    def test_normal_is_transversal_baseline_not_shared_insight(self):
        plan = self.plan()
        self.assertEqual(plan.profile['description'], 'baseline transversal de operación')
        self.assertEqual(plan.counts, {event_type:3 for event_type in validators()})
        self.assertEqual(set(plan.profile['verticals']), {'V1','V2','V3','V4'})

    def test_approved_scenario_verticals(self):
        profiles = scenarios.definitions()['profiles']
        self.assertEqual(profiles['DELIVERY_DELAY']['verticals'], {'V1':'principal','V3':'principal'})
        for name in ('TELEMETRY_ANOMALY','WAREHOUSE_EQUIPMENT_DEGRADATION'):
            self.assertEqual(profiles[name]['verticals'], {'V1':'principal','V4':'principal'})
        self.assertNotIn('V4', profiles['HIGH_DEMAND']['verticals'])

    def test_normal_and_high_demand_correlations(self):
        for name in ('NORMAL','HIGH_DEMAND'):
            plan = self.plan(name)
            selected = [e for e in plan.events if e['event_type'] in ('clic_event','iot_event','stock_event')]
            self.assertEqual(len({e['payload']['store_id'] for e in selected}), 1)
            self.assertEqual(len({e['payload']['product_id'] for e in selected if 'product_id' in e['payload']}), 1)
            stock = self.events(plan,'stock_event')
            self.assertEqual(len({e['payload']['shelf_id'] for e in stock}), 1)
        plan = self.plan()
        iot = self.events(plan,'iot_event'); thermal = self.events(plan,'telemetry_event')
        warehouse = self.events(plan,'warehouse_sensor_event')
        self.assertNotEqual(iot[0]['payload']['device_id'], thermal[0]['payload']['device_id'])
        self.assertEqual(thermal[0]['payload']['warehouse_id'], warehouse[0]['payload']['warehouse_id'])
        self.assertEqual(len({e['payload']['device_id'] for e in iot}), 1)
        self.assertEqual(len({e['payload']['device_id'] for e in thermal}), 1)

    def test_normal_approved_values_actions_and_route(self):
        plan = self.plan()
        values = lambda event_type,key: [e['payload'][key] for e in self.events(plan,event_type)]
        self.assertEqual(values('clic_event','action'), ['VIEW_PRODUCT','CLICK','ADD_TO_CART'])
        self.assertEqual(len(set(values('clic_event','session_id'))), 1)
        self.assertEqual(values('iot_event','value'), [12,13,12])
        self.assertEqual(values('stock_event','stock_quantity'), [30,29,28])
        self.assertEqual(values('telemetry_event','value'), [4.5,4.6,4.5])
        self.assertEqual(values('warehouse_sensor_event','value'), [2.5,2.6,2.5])
        self.assertEqual(values('location_event','delivery_status'), ['IN_TRANSIT','IN_TRANSIT','DELIVERED'])
        self.assertEqual(values('location_event','speed_kmh'), [4.7,4.7,0])
        self.assertEqual(values('location_event','latitude'), [-12.087,-12.0865,-12.086])
        self.assertEqual(values('location_event','longitude'), [-77.051,-77.0505,-77.05])
        # customer_id opcional no pasa a ser requerido por el contexto.
        self.assertTrue(all('customer_id' not in e['payload'] for e in self.events(plan,'clic_event')))

    def test_high_demand_evolution_and_three_ordered_sessions(self):
        plan = self.plan('HIGH_DEMAND')
        clicks = self.events(plan,'clic_event')
        self.assertEqual(len({e['payload']['session_id'] for e in clicks}), 3)
        for i in range(0,6,2):
            pair = clicks[i:i+2]
            self.assertEqual(pair[0]['payload']['session_id'], pair[1]['payload']['session_id'])
            self.assertEqual([e['payload']['action'] for e in pair], ['VIEW_PRODUCT','ADD_TO_CART'])
        self.assertEqual([e['payload']['value'] for e in self.events(plan,'iot_event')], [12,24,36])
        self.assertEqual([e['payload']['stock_quantity'] for e in self.events(plan,'stock_event')], [30,22,14])
        offsets = [(scenarios.parse_start_time(e['event_timestamp'])-plan.start_time).total_seconds() for e in clicks]
        self.assertEqual(offsets,[0,10,20,30,40,50])

    def test_low_stock_snapshots_and_capacity(self):
        plan = self.plan('LOW_STOCK')
        self.assertEqual([e['payload']['stock_quantity'] for e in plan.events],[8,3,0])
        self.assertEqual([e['payload']['stock_capacity'] for e in plan.events],[40,40,40])

    def test_delivery_commitment_constant_and_late_confirmation(self):
        for name in ('NORMAL','DELIVERY_DELAY'):
            plan = self.plan(name)
            events = self.events(plan,'location_event')
            for field in ('delivery_id','order_id','vehicle_id','expected_delivery_timestamp'):
                self.assertEqual(len({e['payload'][field] for e in events}),1)
            promised = scenarios.parse_start_time(events[0]['payload']['expected_delivery_timestamp'])
            self.assertEqual(promised-plan.start_time,timedelta(seconds=120))
        plan = self.plan('DELIVERY_DELAY')
        self.assertEqual([(scenarios.parse_start_time(e['event_timestamp'])-plan.start_time).total_seconds() for e in plan.events], [0,60,180,240])
        self.assertEqual([e['payload']['speed_kmh'] for e in plan.events],[4.7,0,0,0])
        self.assertEqual(plan.events[1]['payload']['latitude'], plan.events[2]['payload']['latitude'])
        self.assertEqual(plan.events[1]['payload']['longitude'], plan.events[2]['payload']['longitude'])
        self.assertEqual(plan.events[-1]['payload']['delivery_status'],'DELIVERED')
        self.assertEqual(scenarios.parse_start_time(plan.events[-1]['event_timestamp'])-promised,timedelta(seconds=120))

    def test_thermal_and_equipment_evolution_stable_assets(self):
        plan = self.plan('TELEMETRY_ANOMALY')
        self.assertEqual([e['payload']['value'] for e in plan.events],[4.5,4.6,9.0,12.0])
        self.assertEqual(len({e['payload']['device_id'] for e in plan.events}),1)
        plan = self.plan('WAREHOUSE_EQUIPMENT_DEGRADATION')
        self.assertEqual([e['payload']['value'] for e in plan.events],[2.5,3.5,5.0,7.0,9.0])
        for field in ('sensor_id','equipment_id','warehouse_id'):
            self.assertEqual(len({e['payload'][field] for e in plan.events}),1)
        for name in ('NORMAL','HIGH_DEMAND','TELEMETRY_ANOMALY','WAREHOUSE_EQUIPMENT_DEGRADATION'):
            for event in self.plan(name).events:
                if 'status' in event['payload']:
                    self.assertEqual(event['payload']['status'],'ACTIVE')

    def test_temporal_order_and_stable_equal_time_order(self):
        for name in EXPECTED_COUNTS:
            plan = self.plan(name)
            times = [e['event_timestamp'] for e in plan.events]
            self.assertEqual(times,sorted(times))
        at_start = self.plan().events[:6]
        self.assertEqual([e['event_type'] for e in at_start], ['clic_event','iot_event',
            'stock_event','location_event','telemetry_event','warehouse_sensor_event'])

    def test_dry_run_all_profiles_without_gcp_or_auth(self):
        with patch('producers.streaming.run_scenario.check_operator') as auth, \
             patch('producers.streaming.run_scenario.publish') as publish, \
             patch('subprocess.run',side_effect=AssertionError('gcloud forbidden')), \
             patch.object(socket,'socket',side_effect=AssertionError('network forbidden')):
            for name,count in EXPECTED_COUNTS.items():
                self.out = io.StringIO()
                status,result = self.cli('--scenario',name,'--dry-run')
                self.assertEqual(status,0)
                self.assertEqual(result['validated_count'],count)
                self.assertEqual(result['confirmed_count'],0)
                self.assertTrue(all(r['message_id'] is None and r['status']=='VALIDATED' for r in result['records']))
                self.assertEqual(result['topic'],'projects/retailsmart-test/topics/rs-dev-str-ps-events')
            auth.assert_not_called();publish.assert_not_called()

    def test_default_mode_and_entire_dry_run_report_reproducible(self):
        status,first = self.cli('--scenario','NORMAL')
        first_bytes = self.out.getvalue()
        self.out = io.StringIO()
        status,second = self.cli('--scenario','NORMAL')
        self.assertEqual(status,0)
        self.assertEqual(first['mode'],'DRY_RUN')
        self.assertEqual(first_bytes,self.out.getvalue())
        self.assertEqual(first,second)

    def test_invalid_last_event_blocks_all_publication(self):
        plan = self.plan('LOW_STOCK');plan.events[-1]['payload']['stock_quantity']=1000
        with patch('producers.streaming.run_scenario.build_plan',return_value=plan), \
             patch('producers.streaming.run_scenario.check_operator') as auth, \
             patch('producers.streaming.run_scenario.publish') as publish:
            status,result = self.cli(*self.publish_args())
        self.assertEqual(status,1);self.assertEqual(result['stage'],'VALIDATE')
        self.assertEqual(result['confirmed_count'],0)
        auth.assert_not_called();publish.assert_not_called()

    def test_broken_identifier_relation_blocks_all_publication(self):
        plan=self.plan('LOW_STOCK');plan.events[-1]['payload']['shelf_id']='other-shelf'
        with patch('producers.streaming.run_scenario.build_plan',return_value=plan), \
             patch('producers.streaming.run_scenario.check_operator') as auth, \
             patch('producers.streaming.run_scenario.publish') as publish:
            status,result=self.cli(*self.publish_args())
        self.assertEqual(status,1);self.assertEqual(result['stage'],'VALIDATE')
        auth.assert_not_called();publish.assert_not_called()

    def test_duplicate_ids_and_wrong_time_rejected(self):
        plan=self.plan('LOW_STOCK');plan.events[1]['event_id']=plan.events[0]['event_id']
        with self.assertRaisesRegex(ValueError,'duplicado'):
            scenarios.serialize_plan(plan)
        plan=self.plan('LOW_STOCK');plan.events[-1]['event_timestamp']=START
        with self.assertRaisesRegex(ValueError,'cronología'):
            scenarios.serialize_plan(plan)

    def test_commitment_changes_and_delivered_regression_rejected(self):
        data=scenarios.definitions()
        data['profiles']['DELIVERY_DELAY']['steps'][1]['commitment_offset_seconds']=180
        with patch.object(scenarios,'definitions',return_value=data):
            plan=self.plan('DELIVERY_DELAY')
            with self.assertRaisesRegex(ValueError,'compromiso'):
                scenarios.serialize_plan(plan)
        data=scenarios.definitions()
        data['profiles']['DELIVERY_DELAY']['steps'][0]['values']['delivery_status']='DELIVERED'
        with patch.object(scenarios,'definitions',return_value=data):
            with self.assertRaisesRegex(ValueError,'confirmada'):
                scenarios.serialize_plan(self.plan('DELIVERY_DELAY'))

    def test_mock_publish_exact_prevalidated_strings_and_order(self):
        expected=scenarios.serialize_plan(self.plan('LOW_STOCK'))
        with patch('producers.streaming.run_scenario.check_operator') as auth, \
             patch('producers.streaming.run_scenario.publish',side_effect=['id-1','id-2','id-3']) as publish:
            status,result=self.cli(*self.publish_args())
        self.assertEqual(status,0);auth.assert_called_once()
        self.assertEqual([c.args[2] for c in publish.call_args_list],list(expected))
        self.assertTrue(all(len(c.args)==3 and not c.kwargs for c in publish.call_args_list))
        self.assertEqual(result['confirmed_count'],3)
        self.assertEqual([r['message_id'] for r in result['records']],['id-1','id-2','id-3'])

    def test_serialized_messages_survive_later_plan_mutation(self):
        plan=self.plan('LOW_STOCK')
        expected=scenarios.serialize_plan(plan)
        def mutate_after_validation(config):
            plan.events[0]['payload']['stock_quantity']=9999
        with patch('producers.streaming.run_scenario.build_plan',return_value=plan), \
             patch('producers.streaming.run_scenario.check_operator',side_effect=mutate_after_validation), \
             patch('producers.streaming.run_scenario.publish',side_effect=['id-1','id-2','id-3']) as publish:
            status,result=self.cli(*self.publish_args())
        self.assertEqual(status,0)
        self.assertEqual([c.args[2] for c in publish.call_args_list],list(expected))
        self.assertEqual(result['events'][0]['payload']['stock_quantity'],8)

    def test_partial_failure_preserves_acks_and_stops_without_retry(self):
        with patch('producers.streaming.run_scenario.check_operator'), \
             patch('producers.streaming.run_scenario.publish',side_effect=[
                 'id-1',transport.PublicationError('timeout',True)]) as publish:
            status,result=self.cli(*self.publish_args())
        self.assertEqual(status,1);self.assertEqual(publish.call_count,2)
        self.assertEqual([r['status'] for r in result['records']],['OK','UNCERTAIN','PENDING'])
        self.assertEqual(result['confirmed_count'],1)
        self.assertEqual(result['pending_count'],1)
        self.assertEqual(result['uncertain_count'],1)

    def test_denied_publish_and_operator_failure_never_continue(self):
        with patch('producers.streaming.run_scenario.check_operator'), \
             patch('producers.streaming.run_scenario.publish',side_effect=transport.PublicationError('denied')) as publish:
            status,result=self.cli(*self.publish_args())
        self.assertEqual(status,1);self.assertEqual(publish.call_count,1)
        self.assertEqual([r['status'] for r in result['records']],['ERROR','PENDING','PENDING'])
        self.out=io.StringIO()
        with patch('producers.streaming.run_scenario.check_operator',side_effect=RuntimeError('operator mismatch')), \
             patch('producers.streaming.run_scenario.publish') as publish:
            status,result=self.cli(*self.publish_args())
        self.assertEqual(status,1);self.assertEqual(result['stage'],'OPERATOR')
        self.assertEqual(result['pending_count'],3);publish.assert_not_called()

    def test_adapter_does_not_add_scenario_attributes(self):
        from infra.config.settings import load
        config,resources=load(self.path)
        message=scenarios.serialize_plan(self.plan('LOW_STOCK'))[0]
        with patch.object(transport,'_run',return_value={'messageIds':['mock-id']}) as run:
            transport.publish(config,resources,message)
        self.assertFalse(any(arg.startswith('--attribute') for arg in run.call_args.args[1:]))
        self.assertIn('--message='+message,run.call_args.args)

    def test_invalid_control_inputs_and_profiles(self):
        for value in ('',' ','run with spaces'):
            with self.assertRaises(ValueError):scenarios.build_plan('NORMAL',value,START)
        for value in ('bad','2026-02-30T12:00:00Z','2026-10-21T12:00:00+00:00','9999-12-31T23:59:59Z'):
            with self.assertRaises(ValueError):scenarios.build_plan('NORMAL','run',value)
        with self.assertRaises(ValueError):scenarios.build_plan('UNAPPROVED')
        for mutate in ('too_many','unsorted','negative'):
            data=scenarios.definitions();steps=data['profiles']['NORMAL']['steps']
            if mutate=='too_many':steps.append(deepcopy(steps[-1]))
            if mutate=='unsorted':steps[-1]['offset_seconds']=0
            if mutate=='negative':steps[0]['offset_seconds']=-1
            with patch.object(scenarios,'definitions',return_value=data):
                with self.assertRaises(ValueError):self.plan()

    def test_publish_requires_explicit_context_and_rejects_scope_extensions(self):
        cases=[['--scenario','NORMAL','--publish'],
               ['--scenario','NORMAL','--publish','--run-id','run'],
               ['--scenario','NORMAL','--publish','--run-id','run','--start-time',START,'--dry-run']]
        for flag in ('--seed','--count','--rate','--topic'):
            cases.append(['--scenario','NORMAL',flag,'1'])
        for args in cases:
            with self.subTest(args=args),redirect_stderr(self.err), \
                 patch('producers.streaming.run_scenario.publish') as publish:
                with self.assertRaises(SystemExit) as error:main(args)
                self.assertEqual(error.exception.code,2)
            publish.assert_not_called()

    def test_scenario_context_does_not_leak_to_unit_cli(self):
        scenarios.serialize_plan(self.plan())
        with redirect_stdout(self.out),redirect_stderr(self.err), \
             patch('subprocess.run',side_effect=AssertionError('gcloud forbidden')):
            status=unit_main(['--type','stock_event','--dry-run','--config',str(self.path)])
        result=json.loads(self.out.getvalue())
        self.assertEqual(status,0);validate_event(result['event'])
        self.assertEqual(result['event']['payload']['stock_quantity'],12)
        first,second=builder.build_stock_event(),builder.build_stock_event()
        self.assertNotEqual(first['event_id'],second['event_id'])
