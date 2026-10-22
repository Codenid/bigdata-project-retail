"""Seguridad de ACK y recepción puntual, sin acceso real a GCP."""
import base64
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from infra.config.settings import ROOT
from producers.streaming.scenarios import build_plan, serialize_plan
from consumers.streaming import pubsub
from consumers.streaming.pull_events import inspect, main
from consumers.streaming.verify_phase33 import combine_reports, content_hash, load_manifest, match, summarize


class Reception(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = load_manifest()
        cls.events = {}
        contexts = {(r['scenario'], r['run_id'], r['start_time']) for r in cls.manifest['events']}
        for context in contexts:
            for raw in serialize_plan(build_plan(*context)):
                event = json.loads(raw)
                cls.events[event['event_id']] = event

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = Path(self.tmp.name) / 'test.env'
        text = (ROOT/'config/dev.env.example').read_text()
        for key, value in dict(GCP_PROJECT_ID='retailsmart-bigdata', GCP_REGION='us-central1',
                               GCP_LOCATION='us-central1', RESOURCE_SUFFIX='rsg',
                               BOOTSTRAP_ACCOUNT='bootstrap@example.com', OPERATOR_ACCOUNT='operator@example.com').items():
            text = text.replace(key+'=\n', key+'='+value+'\n')
        self.config.write_text(text)
        self.out, self.err = io.StringIO(), io.StringIO()

    def row(self, index=0, event=None, mid=None):
        expected = self.manifest['events'][index]
        event = deepcopy(event if event is not None else self.events[expected['event_id']])
        return dict(ackId='sensitive-ack-'+str(index), message=dict(
            messageId=mid or expected['message_id'], data=base64.b64encode(
                json.dumps(event).encode()).decode(), attributes={'internal': 'sensitive-attribute'}))

    def cli(self, rows, *args, error=None):
        with patch('consumers.streaming.pull_events.Client') as factory:
            client = factory.return_value
            client.pull.return_value = rows
            if error:
                getattr(client, error[0]).side_effect = error[1]
            with redirect_stdout(self.out), redirect_stderr(self.err):
                status = main(['--config', str(self.config), *args])
        return status, json.loads(self.out.getvalue()), client

    def test_manifest_reconstructs_all_46_and_matches_publication_ids(self):
        evidence = (ROOT/self.manifest['source']).read_text()
        for expected in self.manifest['events']:
            event = self.events[expected['event_id']]
            self.assertEqual(content_hash(event), expected['sha256'])
            self.assertEqual(match(event, expected['message_id'], self.manifest), 'EXPECTED')
            self.assertIn('| '+expected['message_id']+' | OK |', evidence)
        self.assertEqual(len(self.events), 46)

    def test_offline_combination_handles_order_and_redelivery(self):
        first,_ = inspect([self.row(i) for i in range(23)],self.manifest)
        second,_ = inspect([self.row(i) for i in reversed(range(46))],self.manifest)
        result=combine_reports([{'records':first},{'records':second}],self.manifest)
        self.assertEqual(result['state'],'COMPLETE')
        self.assertEqual(result['deliveries'],69)
        self.assertEqual(result['duplicates'],23)

    def test_offline_combination_detects_conflicting_delivery(self):
        first,_=inspect([self.row()],self.manifest)
        second=deepcopy(first);second[0]['content_sha256']='0'*64
        result=combine_reports([{'records':first},{'records':second}],self.manifest)
        self.assertEqual(result['expected_found'],0)
        self.assertEqual(result['conflicts'],2)

    def test_hash_ignores_json_layout_but_not_content(self):
        row=self.row()
        event=json.loads(base64.b64decode(row['message']['data']))
        row['message']['data']=base64.b64encode(json.dumps(event,indent=4,sort_keys=True).encode()).decode()
        records,_=inspect([row],self.manifest)
        self.assertEqual(records[0]['phase33'],'EXPECTED')

    def test_expected_distribution(self):
        self.assertEqual(summarize([], self.manifest)['expected_by_type'], {
            'clic_event':9,'iot_event':6,'stock_event':9,'location_event':7,
            'telemetry_event':7,'warehouse_sensor_event':8})

    def test_ack_requires_verification_before_config_or_network(self):
        with patch('consumers.streaming.pull_events.load') as load, redirect_stderr(self.err):
            with self.assertRaises(SystemExit) as error:
                main(['--ack'])
            self.assertEqual(error.exception.code, 2)
            load.assert_not_called()

    def test_reject_invalid_limits(self):
        for limit in ('0','51','-1','abc'):
            with self.subTest(limit=limit), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    main(['--limit',limit])

    def test_no_arbitrary_subscription_option(self):
        with redirect_stderr(self.err), self.assertRaises(SystemExit):
            main(['--subscription','other'])

    def test_default_single_pull_10_without_ack(self):
        status, report, client = self.cli([self.row()])
        self.assertEqual(status,0)
        client.check_access.assert_called_once_with()
        client.pull.assert_called_once_with(10)
        client.acknowledge.assert_not_called()
        self.assertEqual(report['records'][0]['ack_status'],'NOT_ACKED')
        self.assertTrue(report['subscription'].endswith('/rs-dev-str-ps-events-dataflow'))

    def test_complete_reversed_delivery_no_ack(self):
        status, report, client = self.cli([self.row(i) for i in reversed(range(46))], '--limit','46','--verify-phase33')
        self.assertEqual(status,0)
        self.assertEqual(report['phase33']['state'],'COMPLETE')
        self.assertEqual(report['phase33']['expected_found'],46)
        client.pull.assert_called_once_with(46)
        client.acknowledge.assert_not_called()

    def test_partial_is_operational_success(self):
        status, report, _ = self.cli([self.row()], '--verify-phase33')
        self.assertEqual(status,0)
        self.assertEqual(report['phase33']['state'],'PARTIAL')
        self.assertEqual(report['phase33']['expected_missing'],45)

    def test_empty_is_unavailable_not_error(self):
        status, report, client = self.cli([], '--verify-phase33','--ack')
        self.assertEqual(status,0)
        self.assertEqual(report['phase33']['state'],'UNAVAILABLE')
        self.assertEqual(report['phase33']['expected_missing'],46)
        client.acknowledge.assert_not_called()

    def test_ack_only_exact_expected(self):
        foreign = deepcopy(self.events[self.manifest['events'][0]['event_id']])
        foreign['event_id']='00000000-0000-4000-8000-000000000001'
        invalid = self.row(2); invalid['message']['data']='not-base64!'
        status, report, client = self.cli([self.row(),self.row(1,event=foreign,mid='999'),invalid], '--verify-phase33','--ack')
        self.assertEqual(status,1)
        client.acknowledge.assert_called_once_with(['sensitive-ack-0'])
        self.assertEqual([r['ack_status'] for r in report['records']],['ACKED','NOT_ACKED','INVALID'])
        self.assertEqual(report['foreign'],1)

    def test_message_id_mismatch_no_ack(self):
        status, report, client = self.cli([self.row(mid='999')], '--verify-phase33','--ack')
        self.assertEqual(status,1)
        self.assertEqual(report['conflicts'],1)
        client.acknowledge.assert_not_called()

    def test_same_event_changed_valid_content_blocks_all_its_deliveries(self):
        event = deepcopy(self.events[self.manifest['events'][0]['event_id']])
        event['event_timestamp']='2026-10-22T04:32:38.000000Z'
        status, report, client = self.cli([self.row(), self.row(event=event)], '--verify-phase33','--ack')
        self.assertEqual(status,1)
        self.assertEqual(report['conflicts'],2)
        self.assertEqual(report['phase33']['expected_found'],0)
        client.acknowledge.assert_not_called()

    def test_hash_change_is_conflict(self):
        event = deepcopy(self.events[self.manifest['events'][0]['event_id']])
        event['payload']['product_id']='00000000-0000-4000-8000-000000000002'
        records, eligible = inspect([self.row(event=event)], self.manifest)
        self.assertEqual(records[0]['phase33'],'CONFLICT')
        self.assertEqual(eligible,[])

    def test_duplicate_not_counted_twice(self):
        _, report, _ = self.cli([self.row(),self.row()], '--verify-phase33')
        self.assertEqual(report['duplicates'],1)
        self.assertEqual(report['phase33']['expected_found'],1)

    def test_same_message_id_different_event_is_conflict(self):
        records, eligible = inspect([self.row(),self.row(1,mid=self.manifest['events'][0]['message_id'])],self.manifest)
        self.assertTrue(all(r['phase33']=='CONFLICT' for r in records))
        self.assertEqual(eligible,[])

    def test_invalid_encodings_json_and_contract_never_ack(self):
        invalids = [b'\xff',b'not-json',b'[]',b'{}',b'{"event_type":"unknown"}',
                    b'{"a":1,"a":2}',b'{"a":NaN}']
        for raw in invalids:
            with self.subTest(raw=raw):
                row = self.row();row['message']['data']=base64.b64encode(raw).decode()
                records,eligible=inspect([row],self.manifest)
                self.assertEqual(records[0]['ack_status'],'INVALID')
                self.assertEqual(eligible,[])

    def test_malformed_envelopes_are_invalid(self):
        for row in [None,{}, {'message':None}, {'message':{'messageId':'secret-arbitrary-text'}}]:
            records,candidates=inspect([row],self.manifest)
            self.assertEqual(records[0]['validation'],'INVALID')
            self.assertEqual(candidates,[])

    def test_missing_ack_handle_never_ack(self):
        row = self.row(); del row['ackId']
        _,report,client=self.cli([row],'--verify-phase33','--ack')
        self.assertEqual(report['records'][0]['ack_status'],'NOT_ACKED')
        client.acknowledge.assert_not_called()

    def test_permission_failure_prevents_pull_and_no_leaks(self):
        status,report,client=self.cli([], '--verify-phase33',error=('check_access',RuntimeError('secret-token')))
        self.assertEqual(status,1)
        client.pull.assert_not_called()
        self.assertNotIn('secret-token',self.out.getvalue()+self.err.getvalue())
        self.assertEqual(report['stage'],'ACCESS')

    def test_pull_failure_has_no_retry(self):
        status,_,client=self.cli([],error=('pull',RuntimeError('secret-ack-id')))
        self.assertEqual(status,1)
        client.pull.assert_called_once_with(10)
        client.acknowledge.assert_not_called()
        self.assertNotIn('secret-ack-id',self.out.getvalue()+self.err.getvalue())

    def test_ack_failure_keeps_records_without_retry(self):
        status,report,client=self.cli([self.row()], '--verify-phase33','--ack',error=('acknowledge',TimeoutError('secret-token')))
        self.assertEqual(status,1)
        self.assertTrue(report['ack_uncertain'])
        self.assertEqual(report['records'][0]['ack_status'],'NOT_ACKED')
        client.acknowledge.assert_called_once()
        self.assertNotIn('secret-token',self.out.getvalue()+self.err.getvalue())

    def test_report_never_exposes_payload_attributes_or_ack_handles(self):
        _,report,_=self.cli([self.row()], '--verify-phase33')
        text=json.dumps(report)
        for secret in ['sensitive-ack','sensitive-attribute','payload','Authorization']:
            self.assertNotIn(secret,text)

    def test_identity_failure_prevents_access_and_pull(self):
        with patch('consumers.streaming.pull_events.Client', side_effect=RuntimeError('account mismatch')), redirect_stdout(self.out),redirect_stderr(self.err):
            self.assertEqual(main(['--config',str(self.config)]),1)
        self.assertEqual(json.loads(self.out.getvalue())['stage'],'OPERATOR')

    def test_wrong_project_manifest_blocks_network(self):
        self.config.write_text(self.config.read_text().replace('GCP_PROJECT_ID=retailsmart-bigdata','GCP_PROJECT_ID=retailsmart-other'))
        with patch('consumers.streaming.pull_events.Client') as client,redirect_stdout(self.out),redirect_stderr(self.err):
            self.assertEqual(main(['--config',str(self.config),'--verify-phase33']),1)
            client.assert_not_called()


class Transport(unittest.TestCase):
    def client(self):
        client=object.__new__(pubsub.Client)
        client.subscription='projects/test-project/subscriptions/catalogued'
        client._token='secret-token'
        client._opener=MagicMock()
        return client

    def test_operator_guard_before_token(self):
        with patch.object(pubsub,'check_operator',side_effect=RuntimeError('mismatch')),patch.object(pubsub.subprocess,'run') as run:
            with self.assertRaises(RuntimeError):pubsub.Client({}, {})
            run.assert_not_called()

    def test_token_selected_operator_not_bootstrap(self):
        config=dict(GCP_PROJECT_ID='test-project',OPERATOR_ACCOUNT='operator@example.com',BOOTSTRAP_ACCOUNT='bootstrap@example.com')
        with patch.object(pubsub,'check_operator') as guard,patch.object(pubsub.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'secret-token\n','')) as run:
            client=pubsub.Client(config,{'RS-STR-002':{'name':'catalogued'}})
        guard.assert_called_once_with(config)
        self.assertIn('--account=operator@example.com',run.call_args.args[0])
        self.assertNotIn('--account=bootstrap@example.com',run.call_args.args[0])
        self.assertEqual(client.subscription,'projects/test-project/subscriptions/catalogued')

    def test_token_failure_sanitized(self):
        config=dict(GCP_PROJECT_ID='test-project',OPERATOR_ACCOUNT='operator@example.com')
        with patch.object(pubsub,'check_operator'),patch.object(pubsub.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'secret-token','secret-error')):
            with self.assertRaises(pubsub.TransportError) as error:pubsub.Client(config,{'RS-STR-002':{'name':'catalogued'}})
        self.assertNotIn('secret',str(error.exception))

    def test_rest_only_unary_pull_without_return_immediately(self):
        client=self.client()
        with patch.object(client,'_post',return_value={}) as post:
            self.assertEqual(client.pull(46),[])
        post.assert_called_once_with('pull',{'maxMessages':46})

    def test_transport_rejects_invalid_limits(self):
        for limit in [0,51,True,'10']:
            with self.assertRaises(ValueError):self.client().pull(limit)

    def test_pull_malformed_response(self):
        for result in [{'receivedMessages':None},{'receivedMessages':[{},{}]}]:
            client=self.client()
            with patch.object(client,'_post',return_value=result),self.assertRaises(pubsub.TransportError):client.pull(1)

    def test_check_consume_before_pull(self):
        client=self.client()
        with patch.object(client,'_post',return_value={'permissions':[pubsub.PERMISSION]}) as post:client.check_access()
        post.assert_called_once_with('testIamPermissions',{'permissions':[pubsub.PERMISSION]})

    def test_missing_permission_stops(self):
        client=self.client()
        with patch.object(client,'_post',return_value={}),self.assertRaises(pubsub.TransportError):client.check_access()

    def test_http_error_sanitized_and_no_retry(self):
        client=self.client()
        client._opener.open.side_effect=HTTPError('https://pubsub.googleapis.com',403,'sensitive-response',{},None)
        with self.assertRaises(pubsub.TransportError) as error:client._post('pull',{'maxMessages':1})
        self.assertIn(pubsub.PERMISSION,str(error.exception))
        self.assertNotIn('sensitive-response',str(error.exception))
        client._opener.open.assert_called_once()

    def test_timeout_no_retry(self):
        client=self.client();client._opener.open.side_effect=URLError('secret-token')
        with self.assertRaises(pubsub.TransportError) as error:client._post('acknowledge',{'ackIds':['secret-ack']})
        self.assertNotIn('secret',str(error.exception))
        client._opener.open.assert_called_once()

    def test_no_redirect_of_authorization(self):
        self.assertIsNone(pubsub.NoRedirect().redirect_request(None,None,302,'',{},'https://other.example'))

    def test_ack_batch_exactly_once(self):
        client=self.client()
        with patch.object(client,'_post',return_value={}) as post:client.acknowledge(['private-a','private-b'])
        post.assert_called_once_with('acknowledge',{'ackIds':['private-a','private-b']})

    def test_invalid_ack_response(self):
        client=self.client()
        with patch.object(client,'_post',return_value={'unexpected':True}),self.assertRaises(pubsub.TransportError):client.acknowledge(['private'])


if __name__=='__main__':
    unittest.main()
