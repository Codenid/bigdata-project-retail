"""Engine con transporte simulado y tiempos acotados; nunca accede a GCP."""
from copy import deepcopy
import io
import json
import math
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from contracts.streaming.validation import validate_event
from infra.config.settings import ROOT, load
from producers.emulator.engine import ProducerEngine
from producers.emulator.sources import SOURCES, compatible
from producers.emulator.transport import OperatorPublisher, NoRedirect
from producers.streaming.publish import PublicationError, publish


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        path=Path(cls.tmp.name)/'test.env'
        text=(ROOT/'config/dev.env.example').read_text()
        for key,value in dict(GCP_PROJECT_ID='retailsmart-test',GCP_REGION='us-central1',GCP_LOCATION='us-central1',RESOURCE_SUFFIX='test',BOOTSTRAP_ACCOUNT='bootstrap@example.com',OPERATOR_ACCOUNT='operator@example.com').items():
            text=text.replace(key+'=\n',key+'='+value+'\n')
        path.write_text(text)
        cls.config,cls.resources=load(path)

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def setUp(self):
        self.messages=[]
        self.guard=threading.Lock()
        def transport(config,resources,message):
            with self.guard:
                self.messages.append(json.loads(message))
                return {'messageIds':[str(1000+len(self.messages))]}
        self.transport=transport
        self.engine=ProducerEngine(self.config,self.resources,transport,max_run_seconds=2,lease_seconds=2)
        self.addCleanup(self.engine.close)

    def until(self,predicate,timeout=1.5):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            if predicate():return
            time.sleep(.005)
        self.fail('Condición no alcanzada dentro del tiempo acotado')

    def test_send_once_validates_and_returns_confirmed_message(self):
        self.assertTrue(self.engine.send_once('shelf'))
        self.assertEqual(self.messages[0]['event_type'],'stock_event')
        validate_event(self.messages[0])
        row=self.engine.snapshot()['activity'][0]
        self.assertEqual(row['message_id'],'1001')
        self.assertEqual(row['result'],'OK')
        source=self.engine.snapshot()['sources']['shelf']
        self.assertEqual(source['last_result'],'OK')
        self.assertEqual(source['last_message_id'],'1001')
        self.assertTrue(source['last_publish_time'].endswith('Z'))

    def test_start_stop_no_more_events_after_stop(self):
        self.engine.set_rate('shelf',20)
        self.engine.start_source('shelf')
        self.until(lambda:len(self.messages)>=2)
        self.engine.stop_source('shelf')
        count=len(self.messages);time.sleep(.08)
        self.assertEqual(count,len(self.messages))
        self.assertEqual(self.engine.snapshot()['sources']['shelf']['status'],'STOPPED')

    def test_restart_does_not_bypass_source_rate(self):
        self.engine.start_source('shelf')
        self.until(lambda:len(self.messages)==1)
        self.engine.stop_source('shelf')
        self.engine.start_source('shelf');time.sleep(.08)
        self.engine.stop_source('shelf')
        self.assertEqual(len(self.messages),1)

    def test_source_isolation(self):
        self.engine.start_source('logistics')
        self.until(lambda:len(self.messages)==1)
        snapshot=self.engine.snapshot()
        self.assertEqual(snapshot['sources']['shelf']['produced'],0)
        self.assertTrue(all(e['event_type']=='location_event' for e in self.messages))

    def test_start_all_stop_all(self):
        self.engine.start_all()
        self.until(lambda:len(self.messages)==6)
        self.assertEqual(self.engine.snapshot()['active_sources'],6)
        self.engine.stop_all()
        self.assertEqual(self.engine.snapshot()['active_sources'],0)
        self.assertTrue(all(not s.thread.is_alive() for s in self.engine.states.values()))

    def test_rate_limits_finite_and_hard_ceiling(self):
        for rate in (0,-1,21,float('nan'),float('inf')):
            with self.subTest(rate=rate),self.assertRaises(ValueError):self.engine.set_rate('shelf',rate)
        for rate in (1,2,5,10,20):
            self.engine.set_rate('shelf',rate)
            self.assertEqual(self.engine.snapshot()['sources']['shelf']['rate'],rate)

    def test_rate_change_takes_effect_while_running(self):
        self.engine.start_source('shelf')
        self.until(lambda:len(self.messages)==1)
        self.engine.set_rate('shelf',20)
        self.until(lambda:len(self.messages)>=3,timeout=.5)
        self.engine.stop_source('shelf')

    def test_manual_send_rate_protected(self):
        self.engine.send_once('shelf')
        with self.assertRaises(RuntimeError):self.engine.send_once('shelf')
        self.assertEqual(len(self.messages),1)

    def test_idempotent_start_does_not_create_second_worker(self):
        self.engine.start_source('shelf');thread=self.engine.states['shelf'].thread
        self.engine.start_source('shelf')
        self.assertIs(thread,self.engine.states['shelf'].thread)

    def test_send_once_disallowed_while_running(self):
        self.engine.start_source('shelf')
        with self.assertRaises(RuntimeError):self.engine.send_once('shelf')

    def test_invalid_event_blocks_publish_and_stops_source(self):
        with patch('producers.emulator.engine.validate_event',side_effect=ValueError('bad contract')):
            self.engine.start_source('shelf')
            self.until(lambda:self.engine.snapshot()['sources']['shelf']['errors']==1)
            self.until(lambda:self.engine.snapshot()['active_sources']==0)
        self.assertEqual(self.messages,[])
        self.assertEqual(self.engine.snapshot()['failed_publishes'],1)

    def test_failure_not_retried_and_secret_not_logged(self):
        self.engine.transport=lambda *args:(_ for _ in ()).throw(RuntimeError('secret-credential'))
        self.engine.start_source('shelf')
        self.until(lambda:self.engine.snapshot()['failed_publishes']==1)
        self.until(lambda:self.engine.snapshot()['active_sources']==0)
        time.sleep(.08)
        snapshot=self.engine.snapshot()
        self.assertEqual(snapshot['total_produced'],1)
        self.assertNotIn('secret-credential',json.dumps(snapshot))
        self.assertIsNone(snapshot['activity'][0]['message_id'])
        self.assertEqual(snapshot['sources']['shelf']['last_result'],'ERROR')

    def test_metrics_exact_counts(self):
        self.engine.send_once('shelf');self.engine.send_once('iot')
        snapshot=self.engine.snapshot()
        self.assertEqual(snapshot['total_produced'],2)
        self.assertEqual(snapshot['successful_publishes'],2)
        self.assertEqual(snapshot['failed_publishes'],0)
        self.assertEqual(snapshot['current_total_rate'],0)

    def test_activity_capped_and_snapshot_is_copy(self):
        clock=[time.monotonic()]
        def now():clock[0]+=.1;return clock[0]
        with patch('producers.emulator.engine.time.monotonic',side_effect=now):
            self.engine.heartbeat();self.engine.set_rate('shelf',20)
            for _ in range(55):
                self.engine.heartbeat();self.engine.send_once('shelf')
        snapshot=self.engine.snapshot()
        self.assertEqual(len(snapshot['activity']),50)
        snapshot['activity'][0]['event']['payload']['stock_quantity']=999
        self.assertNotEqual(self.engine.snapshot()['activity'][0]['event']['payload']['stock_quantity'],999)

    def test_scenario_compatibility(self):
        self.engine.set_scenario('TELEMETRY_ANOMALY')
        self.assertTrue(compatible('cold_room',self.engine.scenario))
        with self.assertRaises(ValueError):self.engine.start_source('shelf')

    def test_scenario_finite_values_and_automatic_stop(self):
        self.engine.set_scenario('TELEMETRY_ANOMALY')
        self.engine.set_rate('cold_room',20)
        self.engine.start_all()
        self.until(lambda:self.engine.snapshot()['active_sources']==0)
        self.assertEqual([e['payload']['value'] for e in self.messages],[4.5,4.6,9,12])
        self.assertEqual(len({e['event_id'] for e in self.messages}),4)
        self.assertTrue(all('scenario' not in e for e in self.messages))

    def test_scenario_restart_new_logical_execution(self):
        self.engine.set_scenario('TELEMETRY_ANOMALY');self.engine.set_rate('cold_room',20)
        self.engine.start_source('cold_room');self.until(lambda:self.engine.snapshot()['active_sources']==0)
        first={e['event_id'] for e in self.messages}
        self.engine.start_source('cold_room');self.until(lambda:self.engine.snapshot()['active_sources']==0)
        self.assertFalse(first & {e['event_id'] for e in self.messages[4:]})

    def test_scenario_correlations_shared_across_sources(self):
        self.engine.set_scenario('HIGH_DEMAND')
        for source in SOURCES:self.engine.set_rate(source.id,20)
        self.engine.start_all();self.until(lambda:self.engine.snapshot()['active_sources']==0)
        self.assertEqual(len(self.messages),12)
        self.assertEqual(len({e['payload']['store_id'] for e in self.messages}),1)
        self.assertEqual(self.engine.snapshot()['sources']['logistics']['produced'],0)

    def test_scenario_cannot_change_while_running(self):
        self.engine.start_source('shelf')
        with self.assertRaises(RuntimeError):self.engine.set_scenario('LOW_STOCK')

    def test_plan_invalid_blocks_all_sources_before_publish(self):
        self.engine.set_scenario('NORMAL')
        with patch('producers.emulator.engine.serialize_plan',side_effect=ValueError('invalid plan')),self.assertRaises(ValueError):
            self.engine.start_all()
        self.assertEqual(self.messages,[])
        self.assertEqual(self.engine.snapshot()['active_sources'],0)

    def test_close_safe_idempotent(self):
        self.engine.start_all();self.until(lambda:len(self.messages)==6)
        self.engine.close();self.engine.close()
        self.assertTrue(self.engine.snapshot()['closed'])
        self.assertTrue(all(not s.thread.is_alive() for s in self.engine.states.values()))
        with self.assertRaises(RuntimeError):self.engine.start_source('shelf')

    def test_session_disconnect_expires_without_orphans(self):
        self.engine.lease_seconds=.08
        self.engine.start_source('shelf')
        self.until(lambda:self.engine.snapshot()['active_sources']==0)
        self.assertFalse(self.engine.states['shelf'].thread.is_alive())

    def test_maximum_run_window(self):
        self.engine.max_run_seconds=.09
        self.engine.set_rate('shelf',20);self.engine.start_source('shelf')
        self.until(lambda:self.engine.snapshot()['active_sources']==0)
        self.assertLessEqual(len(self.messages),2)

    def test_close_waits_for_inflight_and_prevents_another_send(self):
        entered=threading.Event();release=threading.Event()
        def transport(*args):entered.set();release.wait(1);return {'messageIds':['1001']}
        self.engine.transport=transport
        self.engine.start_source('shelf');self.assertTrue(entered.wait(.5))
        timer=threading.Timer(.04,release.set);timer.start()
        self.engine.close();timer.join()
        self.assertEqual(self.engine.snapshot()['successful_publishes'],1)
        self.assertFalse(self.engine.states['shelf'].thread.is_alive())

    def test_no_batch_source_implemented(self):
        self.assertEqual(len(SOURCES),6)
        self.assertTrue(all(s.kind=='streaming' for s in SOURCES))

    def test_transport_hook_reuses_publication_response_guard(self):
        with self.assertRaises(PublicationError):publish(self.config,self.resources,'{}',transport=lambda *args:{'messageIds':[]})
        self.assertEqual(publish(self.config,self.resources,'{}',transport=lambda *args:{'messageIds':['123']}),'123')

    def test_invalid_constructor_limits(self):
        for kwargs in [dict(max_rate=21),dict(max_rate=float('nan')),dict(max_run_seconds=301),dict(lease_seconds=11)]:
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):ProducerEngine(self.config,self.resources,self.transport,**kwargs)


class RestTransportTests(unittest.TestCase):
    def transport(self):
        instance=object.__new__(OperatorPublisher)
        instance._token='secret-token';instance._target='projects/test-project/topics/catalogued'
        instance._operator='operator@example.com';instance._expires=time.monotonic()+60;instance.timeout=5
        return instance

    def test_identity_checked_before_token(self):
        with patch('producers.emulator.transport.check_operator',side_effect=RuntimeError('wrong account')),patch('producers.emulator.transport.subprocess.run') as run:
            with self.assertRaises(RuntimeError):OperatorPublisher({}, {})
            run.assert_not_called()

    def test_no_redirect_of_credentials(self):
        self.assertIsNone(NoRedirect().redirect_request(None,None,302,'',{},'https://other'))

    def test_post_exact_event_and_no_attributes(self):
        transport=self.transport();config=dict(GCP_PROJECT_ID='test-project',OPERATOR_ACCOUNT='operator@example.com');resources={'RS-STR-001':{'name':'catalogued'}}
        with patch('producers.emulator.transport.build_opener') as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value=b'{"messageIds":["123"]}'
            self.assertEqual(transport(config,resources,'{"event_id":"test"}'),{'messageIds':['123']})
        request=opener.return_value.open.call_args.args[0]
        body=json.loads(request.data)
        self.assertEqual(set(body['messages'][0]),{'data'})
        opener.return_value.open.assert_called_once()

    def test_error_is_sanitized_without_retry(self):
        transport=self.transport();config=dict(GCP_PROJECT_ID='test-project',OPERATOR_ACCOUNT='operator@example.com');resources={'RS-STR-001':{'name':'catalogued'}}
        with patch('producers.emulator.transport.build_opener') as opener:
            opener.return_value.open.side_effect=OSError('secret-token')
            with self.assertRaises(RuntimeError) as error:transport(config,resources,'{}')
            self.assertNotIn('secret-token',str(error.exception))
            opener.return_value.open.assert_called_once()

    def test_other_target_or_expired_session_blocked(self):
        transport=self.transport()
        with self.assertRaises(RuntimeError):transport({'GCP_PROJECT_ID':'other-project','OPERATOR_ACCOUNT':'operator@example.com'},{'RS-STR-001':{'name':'other'}},'{}')
        transport._expires=0
        with self.assertRaises(RuntimeError):transport({'GCP_PROJECT_ID':'test-project','OPERATOR_ACCOUNT':'operator@example.com'},{'RS-STR-001':{'name':'catalogued'}},'{}')


if __name__=='__main__':unittest.main()
