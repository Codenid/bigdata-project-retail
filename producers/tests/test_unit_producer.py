"""Productor unitario: contratos reutilizados, identidad operativa y publicación aislada."""
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from contracts.streaming.validation import validate_event, validators
from infra.config.settings import ROOT, load
from producers.streaming import build_event as builder
from producers.streaming import publish as publisher
from producers.streaming.send_event import main


class UnitProducer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'test.env'
        text = (ROOT / 'config/dev.env.example').read_text()
        for key, value in {'GCP_PROJECT_ID': 'retailsmart-test', 'GCP_REGION': 'us-central1',
                           'GCP_LOCATION': 'us-central1', 'RESOURCE_SUFFIX': 'test',
                           'BOOTSTRAP_ACCOUNT': 'bootstrap@example.com',
                           'OPERATOR_ACCOUNT': 'operator@example.com'}.items():
            text = text.replace(key + '=\n', key + '=' + value + '\n')
        self.path.write_text(text)
        self.config, self.resources = load(self.path)
        self.output, self.errors = io.StringIO(), io.StringIO()

    def cli(self, *args):
        with redirect_stdout(self.output), redirect_stderr(self.errors):
            status = main(['--config', str(self.path), *args])
        return status, json.loads(self.output.getvalue().splitlines()[-1])

    def fake_gcloud(self, command, **kwargs):
        self.calls.append(command)
        if command[1:3] == ['auth', 'list']:
            result = [{'account': self.config['OPERATOR_ACCOUNT'], 'status': 'ACTIVE'}]
        elif command[1:4] == ['config', 'list', 'auth/']:
            result = {'auth': {}}
        else:
            self.assertEqual(command[1:4], ['pubsub', 'topics', 'publish'])
            result = {'messageIds': ['message-test-001']}
        return subprocess.CompletedProcess(command, 0, json.dumps(result), '')

    def test_six_factories_produce_valid_events_without_examples(self):
        original_read = Path.read_text
        def read(path, *args, **kwargs):
            self.assertNotIn('examples', path.parts)
            return original_read(path, *args, **kwargs)
        validators.cache_clear(); builder.schema_version.cache_clear()
        with patch.object(Path, 'read_text', read), \
             patch.object(socket, 'socket', side_effect=AssertionError('network forbidden')):
            for event_type in validators():
                with self.subTest(event_type=event_type):
                    event = builder.build_event(event_type)
                    self.assertEqual(event['event_type'], event_type)
                    validate_event(event)

    def test_fact_identifiers_unique_and_mutable_payloads_independent(self):
        for event_type in validators():
            first, second = builder.build_event(event_type), builder.build_event(event_type)
            self.assertNotEqual(first['event_id'], second['event_id'])
            first['payload']['unexpected'] = 1
            self.assertNotIn('unexpected', second['payload'])

    def test_location_new_delivery_and_commitment_from_same_origin_time(self):
        now = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
        with patch.object(builder, 'utc_now', return_value=now):
            first, second = builder.build_location_event(), builder.build_location_event()
        self.assertNotEqual(first['payload']['delivery_id'], second['payload']['delivery_id'])
        self.assertNotEqual(first['payload']['order_id'], second['payload']['order_id'])
        self.assertEqual(first['event_timestamp'], builder.timestamp(now))
        expected = datetime.fromisoformat(first['payload']['expected_delivery_timestamp'].replace('Z', '+00:00'))
        self.assertEqual(expected - now, timedelta(hours=1))

    def test_shared_entities_coherent_between_sources(self):
        click, stock, iot = builder.build_clic_event(), builder.build_stock_event(), builder.build_iot_event()
        self.assertEqual(click['payload']['product_id'], stock['payload']['product_id'])
        self.assertEqual({e['payload']['store_id'] for e in (click, stock, iot)}, {'STORE-SYN-001'})
        self.assertEqual(builder.build_telemetry_event()['payload']['warehouse_id'],
                         builder.build_warehouse_sensor_event()['payload']['warehouse_id'])

    def test_source_and_version_read_from_contract_metadata(self):
        validator = validators()['stock_event']
        original_source = validator.schema['properties']['source']['const']
        try:
            validator.schema['properties']['source']['const'] = 'metadata-from-schema'
            self.assertEqual(builder.build_stock_event()['source'], 'metadata-from-schema')
        finally:
            validator.schema['properties']['source']['const'] = original_source
        common = json.loads((ROOT / 'contracts/streaming/common-event.schema.json').read_text())
        self.assertEqual(builder.build_stock_event()['schema_version'], common['properties']['schema_version']['const'])

    def test_all_six_dry_runs_never_contact_gcloud(self):
        for event_type in validators():
            with self.subTest(event_type=event_type), \
                 patch('producers.streaming.publish.subprocess.run', side_effect=AssertionError('gcloud forbidden')):
                self.output = io.StringIO()
                status, result = self.cli('--type', event_type, '--dry-run')
                self.assertEqual(status, 0)
                self.assertEqual(result['result'], 'OK')
                self.assertEqual(result['mode'], 'DRY_RUN')
                self.assertIsNone(result['message_id'])
                self.assertFalse(result['published'])
                self.assertEqual(result['topic'], 'projects/retailsmart-test/topics/' + self.resources['RS-STR-001']['name'])
                validate_event(result['event'])

    def test_dry_run_does_not_require_operator_auth(self):
        self.path.write_text(self.path.read_text().replace('OPERATOR_ACCOUNT=operator@example.com', 'OPERATOR_ACCOUNT='))
        with patch('producers.streaming.send_event.check_operator') as auth, \
             patch('producers.streaming.send_event.publish') as publish:
            status, _ = self.cli('--type', 'stock_event', '--dry-run')
        self.assertEqual(status, 0)
        auth.assert_not_called(); publish.assert_not_called()

    def test_invalid_event_rejected_before_auth_and_publish(self):
        event = builder.build_stock_event(); event['payload']['stock_quantity'] = 1000
        with patch('producers.streaming.send_event.build_event', return_value=event), \
             patch('producers.streaming.send_event.check_operator') as auth, \
             patch('producers.streaming.send_event.publish') as publish:
            status, result = self.cli('--type', 'stock_event')
        self.assertEqual(status, 1); self.assertEqual(result['stage'], 'VALIDATE')
        auth.assert_not_called(); publish.assert_not_called()

    def test_exact_validated_serialization_reaches_transport_once(self):
        self.calls = []
        with patch('producers.streaming.publish.shutil.which', return_value='/fake/gcloud'), \
             patch('producers.streaming.publish.subprocess.run', side_effect=self.fake_gcloud):
            status, result = self.cli('--type', 'stock_event')
        self.assertEqual(status, 0)
        self.assertEqual(result['message_id'], 'message-test-001')
        publishes = [c for c in self.calls if c[1:4] == ['pubsub', 'topics', 'publish']]
        self.assertEqual(len(publishes), 1)
        sent = next(arg.removeprefix('--message=') for arg in publishes[0] if arg.startswith('--message='))
        self.assertEqual(sent, json.dumps(result['event'], ensure_ascii=False, allow_nan=False, separators=(',', ':')))
        self.assertIn('--account=operator@example.com', publishes[0])
        self.assertNotIn('--account=bootstrap@example.com', publishes[0])
        self.assertEqual(result['topic'], publishes[0][4])
        self.assertTrue(result['published'])
        for key in ('event_type', 'event_id', 'topic', 'message_id', 'timestamp'):
            self.assertTrue(result[key])

    def test_active_account_lookup_does_not_select_or_change_account(self):
        self.calls = []
        with patch('producers.streaming.publish.shutil.which', return_value='/fake/gcloud'), \
             patch('producers.streaming.publish.subprocess.run', side_effect=self.fake_gcloud):
            publisher.check_operator(self.config)
        self.assertFalse(any(arg.startswith('--account') for arg in self.calls[0]))
        self.assertEqual(self.calls[0][1:3], ['auth', 'list'])
        self.assertEqual(self.calls[1][1:4], ['config', 'list', 'auth/'])
        self.assertNotIn('set', repr(self.calls))

    def test_mismatched_or_missing_active_account_prevents_publish(self):
        for accounts in ([], [{'account': 'bootstrap@example.com', 'status': 'ACTIVE'}], ['malformed']):
            with self.subTest(accounts=accounts), patch('producers.streaming.publish._run', return_value=accounts) as run:
                with self.assertRaises(RuntimeError):
                    publisher.check_operator(self.config)
            self.assertEqual(run.call_count, 1)

    def test_no_runtime_fallback_to_bootstrap_identity(self):
        del self.config['OPERATOR_ACCOUNT']
        with patch('producers.streaming.publish._run') as run:
            with self.assertRaisesRegex(ValueError, 'OPERATOR_ACCOUNT'):
                publisher.check_operator(self.config)
        run.assert_not_called()

    def test_inherited_identity_overrides_rejected(self):
        keys = ('impersonate_service_account', 'credential_file_override', 'access_token_file', 'access_token')
        for key in keys:
            with self.subTest(key=key), patch('producers.streaming.publish._run', side_effect=[
                    [{'account': 'operator@example.com'}], {'auth': {key: 'different-identity'}}]):
                with self.assertRaisesRegex(RuntimeError, 'Override'):
                    publisher.check_operator(self.config)
        with patch.dict(os.environ, {'CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT': 'other@example.com'}), \
             patch('producers.streaming.publish._run', side_effect=[
                    [{'account': 'operator@example.com'}], {}]):
            with self.assertRaisesRegex(RuntimeError, 'Override'):
                publisher.check_operator(self.config)

    def test_operator_failure_leaves_publish_uninvoked(self):
        with patch('producers.streaming.send_event.check_operator', side_effect=RuntimeError('account mismatch')), \
             patch('producers.streaming.send_event.publish') as publish:
            status, result = self.cli('--type', 'stock_event')
        self.assertEqual(status, 1); self.assertEqual(result['stage'], 'OPERATOR')
        self.assertIsNone(result['message_id']); publish.assert_not_called()

    def test_denied_publish_reports_permission_without_iam_changes(self):
        response = subprocess.CompletedProcess([], 1, '', 'PERMISSION_DENIED: 403\n')
        with patch('producers.streaming.publish.shutil.which', return_value='/fake/gcloud'), \
             patch('producers.streaming.publish.subprocess.run', return_value=response) as run, \
             redirect_stderr(self.errors):
            with self.assertRaisesRegex(publisher.PublicationError, 'pubsub.topics.publish') as error:
                publisher.publish(self.config, self.resources, '{}')
        self.assertFalse(error.exception.uncertain)
        self.assertEqual(run.call_count, 1)
        self.assertIn('PERMISSION_DENIED', self.errors.getvalue())
        self.assertEqual(run.call_args.args[0][1:4], ['pubsub', 'topics', 'publish'])

    def test_timeout_is_uncertain_and_never_retried(self):
        with patch('producers.streaming.publish._run', side_effect=subprocess.TimeoutExpired('gcloud', 180)) as run:
            with self.assertRaises(publisher.PublicationError) as error:
                publisher.publish(self.config, self.resources, '{}')
        self.assertTrue(error.exception.uncertain); self.assertEqual(run.call_count, 1)

    def test_partial_timeout_stderr_visible(self):
        with patch('producers.streaming.publish.shutil.which', return_value='/fake/gcloud'), \
             patch('producers.streaming.publish.subprocess.run', side_effect=subprocess.TimeoutExpired(
                 'gcloud', 180, stderr=b'network timed out\n')), redirect_stderr(self.errors):
            with self.assertRaises(publisher.PublicationError):
                publisher.publish(self.config, self.resources, '{}')
        self.assertIn('network timed out', self.errors.getvalue())

    def test_missing_message_id_is_not_success(self):
        for response in ({}, {'messageIds': []}, {'messageIds': [None]}, {'messageIds': ['a','b']}, []):
            with self.subTest(response=response), patch('producers.streaming.publish._run', return_value=response) as run:
                with self.assertRaises(publisher.PublicationError) as error:
                    publisher.publish(self.config, self.resources, '{}')
            self.assertTrue(error.exception.uncertain); self.assertEqual(run.call_count, 1)

    def test_network_failure_is_reported_uncertain(self):
        with patch('producers.streaming.publish._run', side_effect=RuntimeError('connection reset')):
            with self.assertRaises(publisher.PublicationError) as error:
                publisher.publish(self.config, self.resources, '{}')
        self.assertTrue(error.exception.uncertain)

    def test_cli_publication_error_never_claims_ok(self):
        with patch('producers.streaming.send_event.check_operator'), patch('producers.streaming.send_event.publish',
                side_effect=publisher.PublicationError('not confirmed', True)):
            status, result = self.cli('--type', 'stock_event')
        self.assertEqual(status, 1); self.assertEqual(result['result'], 'ERROR')
        self.assertFalse(result['published']); self.assertTrue(result['publication_uncertain'])

    def test_configuration_failure_prevents_build_and_publish(self):
        self.path.write_text(self.path.read_text().replace('EVENTS_TOPIC_ID=rs-dev-str-ps-events', 'EVENTS_TOPIC_ID=unapproved'))
        with patch('producers.streaming.send_event.build_event') as build, \
             patch('producers.streaming.send_event.publish') as publish:
            status, result = self.cli('--type', 'stock_event')
        self.assertEqual(status, 1); self.assertEqual(result['stage'], 'CONFIGURATION')
        build.assert_not_called(); publish.assert_not_called()

    def test_unsupported_flags_and_event_names_rejected(self):
        for args in (['--type','click_event'], ['--type','stock_event','--topic','other'],
                     ['--type','stock_event','--count','2'], ['--type','stock_event','--rate','10']):
            with self.subTest(args=args), redirect_stderr(self.errors), \
                 patch('producers.streaming.send_event.publish') as publish:
                with self.assertRaises(SystemExit) as error:
                    main(args)
                self.assertEqual(error.exception.code, 2)
            publish.assert_not_called()

    def test_missing_gcloud_stops_without_invoking_process(self):
        with patch('producers.streaming.publish.shutil.which', return_value=None), \
             patch('producers.streaming.publish.subprocess.run') as run:
            with self.assertRaisesRegex(RuntimeError, 'gcloud'):
                publisher.check_operator(self.config)
        run.assert_not_called()

    def test_environment_override_for_explicit_operator_key(self):
        with patch.dict(os.environ, {'OPERATOR_ACCOUNT': 'other-operator@example.com'}):
            config, _ = load(self.path)
        self.assertEqual(config['OPERATOR_ACCOUNT'], 'other-operator@example.com')
        self.assertEqual(config['BOOTSTRAP_ACCOUNT'], 'bootstrap@example.com')
