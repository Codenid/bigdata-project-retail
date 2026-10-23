"""Interfaz Streamlit real con transporte simulado; no publica en GCP."""
from pathlib import Path
import unittest
import time
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from infra.config.settings import ROOT


class SourceEmulatorUI(unittest.TestCase):
    def app(self):
        app=AppTest.from_file(str(ROOT/'apps/source_emulator.py'),default_timeout=10).run()
        self.assertEqual(len(app.exception),0)
        self.addCleanup(lambda:app.session_state['engine'].close() if app.session_state['engine'] else None)
        return app

    def connect(self,app):
        with patch('producers.emulator.transport.OperatorPublisher',return_value=lambda *args:{'messageIds':['123']}):
            app.button(key='connect_operator').click().run()
        self.assertEqual(len(app.exception),0)

    def test_opens_without_credentials_access_or_publication(self):
        with patch('producers.emulator.transport.OperatorPublisher',side_effect=AssertionError('no auth')):
            app=self.app()
        self.assertIsNone(app.session_state['engine'])
        self.assertTrue(app.button(key='start_shelf').disabled)
        self.assertTrue(app.button(key='test_shelf').disabled)

    def test_batch_coming_next(self):
        app=self.app();app.radio[0].set_value('Batch').run()
        self.assertEqual(len(app.exception),0)
        self.assertTrue(any('Coming next' in str(info.value) for info in app.info))

    def test_source_names_primary(self):
        app=self.app()
        text=' '.join(str(row.value) for row in app.markdown)
        self.assertIn('Estantería Inteligente',text)
        self.assertIn('Tracking Logístico',text)
        self.assertIn('Cámaras Frigoríficas',text)

    def test_connect_and_test_updates_pubsub_observability(self):
        app=self.app();self.connect(app)
        app.button(key='test_shelf').click().run()
        app.run()  # El fragmento periódico refleja el snapshot actualizado.
        self.assertEqual(len(app.exception),0)
        snapshot=app.session_state['engine'].snapshot()
        self.assertEqual(snapshot['successful_publishes'],1)
        self.assertEqual(snapshot['activity'][0]['message_id'],'123')
        self.assertEqual(snapshot['sources']['shelf']['last_result'],'OK')
        self.assertEqual(snapshot['sources']['shelf']['last_message_id'],'123')
        self.assertTrue(snapshot['sources']['shelf']['last_publish_time'].endswith('Z'))
        self.assertTrue(any('CONNECTED' in str(row.value) for row in app.markdown))
        self.assertTrue(any(str(row.value)=='123' for row in app.code))
        app.radio[0].set_value('Activity').run()
        self.assertEqual(len(app.exception),0)
        self.assertEqual(len(app.json),1)

    def test_failed_test_shows_error_without_message_id(self):
        app=self.app()
        with patch('producers.emulator.transport.OperatorPublisher',return_value=lambda *args:(_ for _ in ()).throw(RuntimeError('private detail'))):
            app.button(key='connect_operator').click().run()
        app.button(key='test_shelf').click().run()
        app.run()
        state=app.session_state['engine'].snapshot()['sources']['shelf']
        self.assertEqual(state['last_result'],'ERROR')
        self.assertEqual(state['last_message_id'],'')
        self.assertEqual(state['errors'],1)
        self.assertTrue(any('ERROR' in str(row.value) for row in app.markdown))

    def test_profile_disables_incompatible_sources(self):
        app=self.app();self.connect(app)
        app.selectbox(key='scenario').set_value('TELEMETRY_ANOMALY').run()
        self.assertTrue(app.button(key='start_shelf').disabled)
        self.assertFalse(app.button(key='start_cold_room').disabled)
        self.assertEqual(app.session_state['engine'].scenario,'TELEMETRY_ANOMALY')

    def test_thermal_profile_chart_after_finite_run(self):
        app=self.app();self.connect(app)
        app.selectbox(key='scenario').set_value('TELEMETRY_ANOMALY').run()
        app.selectbox(key='preset_cold_room').set_value('Custom').run()
        app.number_input(key='custom_cold_room').set_value(20.0).run()
        app.button(key='start_cold_room').click().run()
        engine=app.session_state['engine']
        deadline=time.monotonic()+1
        while engine.snapshot()['active_sources'] and time.monotonic()<deadline:
            time.sleep(.01)
        app.run()
        self.assertEqual(len(app.exception),0)
        self.assertEqual(engine.snapshot()['sources']['cold_room']['success'],4)
        self.assertTrue(any('temperatura observada' in str(row.value) for row in app.markdown))

    def test_disconnect_stops_all(self):
        app=self.app();self.connect(app)
        engine=app.session_state['engine']
        engine.start_all()
        app.button(key='disconnect_operator').click().run()
        self.assertIsNone(app.session_state['engine'])
        self.assertTrue(engine.snapshot()['closed'])
        self.assertTrue(all(not state.thread.is_alive() for state in engine.states.values()))


if __name__=='__main__':unittest.main()
