import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions
from apache_beam.testing.test_pipeline import TestPipeline
from apache_beam.testing.util import assert_that, equal_to

from infra.config.settings import ROOT, load
from pipelines.streaming.manage import binding_specs, estimate, main as manage_main, validate_config
from pipelines.streaming.pipeline import ERROR_TAG, ValidateAndRoute, build


class PipelineTests(unittest.TestCase):
    def valid(self, name='stock_event.json'):
        return (ROOT / 'contracts/streaming/examples/valid' / name).read_bytes()

    def test_valid_event_routes_exact_raw_by_type_and_date_direct_runner(self):
        raw = self.valid()
        event = json.loads(raw)
        with TestPipeline(options=PipelineOptions(['--runner=DirectRunner'])) as pipeline:
            routed = (pipeline | beam.Create([raw])
                      | beam.ParDo(ValidateAndRoute()).with_outputs(ERROR_TAG, main='valid'))
            assert_that(routed.valid, equal_to([{
                'destination': f"event_type=stock_event/event_date={event['event_timestamp'][:10]}",
                'line': raw.decode()}]), label='valid exact')
            assert_that(routed.invalid, equal_to([]), label='no errors')

    def test_invalid_event_is_preserved_and_never_silently_dropped(self):
        raw = b'{"event_type":"stock_event","broken":true}'
        def check(rows):
            self.assertEqual(len(rows), 1)
            record = json.loads(rows[0]['line'])
            self.assertEqual(base64.b64decode(record['payload_base64']), raw)
            self.assertTrue(rows[0]['destination'].startswith('errors/ingest_date='))
            self.assertIn(record['error_type'], ('ValidationError', 'KeyError'))
        with TestPipeline(options=PipelineOptions(['--runner=DirectRunner'])) as pipeline:
            routed = (pipeline | beam.Create([raw])
                      | beam.ParDo(ValidateAndRoute()).with_outputs(ERROR_TAG, main='valid'))
            assert_that(routed.valid, equal_to([]), label='no valid')
            assert_that(routed.invalid, check, label='invalid preserved')

    def test_multiple_events_share_type_and_date_destination_direct_runner(self):
        raw = self.valid()
        destination = 'event_type=stock_event/event_date=' + json.loads(raw)['event_timestamp'][:10]
        with TestPipeline(options=PipelineOptions(['--runner=DirectRunner'])) as pipeline:
            routed = (pipeline | beam.Create([raw, raw])
                      | beam.ParDo(ValidateAndRoute()).with_outputs(ERROR_TAG, main='valid'))
            assert_that(routed.valid, equal_to([
                {'destination': destination, 'line': raw.decode()},
                {'destination': destination, 'line': raw.decode()}]))

    def test_streaming_graph_has_distinct_valid_and_error_sinks(self):
        pipeline = beam.Pipeline(options=PipelineOptions(['--runner=DirectRunner']))
        build(pipeline, pipeline | beam.Create([self.valid()]), output_path='gs://bronze/streaming',
              temp_path='gs://technical/fileio', window_seconds=300, shards=1)
        labels = {transform.unique_name for transform in pipeline.to_runner_api().components.transforms.values()}
        self.assertTrue(any('Write valid Bronze' in label for label in labels))
        self.assertTrue(any('Write invalid evidence' in label for label in labels))


class ManagementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        path = Path(cls.temp.name) / 'dev.env'
        text = (ROOT / 'config/dev.env.example').read_text()
        values = {'GCP_PROJECT_ID': 'retailsmart-test', 'GCP_REGION': 'us-central1',
                  'GCP_LOCATION': 'us-central1', 'RESOURCE_SUFFIX': 'test',
                  'BOOTSTRAP_ACCOUNT': 'bootstrap@example.com', 'OPERATOR_ACCOUNT': 'operator@example.com'}
        for key, value in values.items():
            text = text.replace(key + '=\n', key + '=' + value + '\n')
        path.write_text(text)
        cls.config, cls.resources = load(path)
        cls.manifest = json.loads((ROOT / 'infra/config/dataflow.json').read_text())

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_cost_guard_and_minimum_runtime_scopes(self):
        validate_config(self.config, self.resources, self.manifest)
        cost = estimate(self.config, self.manifest)
        self.assertEqual(cost['hourly_usd'], 0.1039)
        specs = binding_specs(self.config, self.resources, self.manifest)
        self.assertEqual(len(specs), 7)
        self.assertIn(('subscription', 'rs-dev-str-ps-events-dataflow', 'roles/pubsub.subscriber',
                       'serviceAccount:rs-dev-str-sa-dataflow@retailsmart-test.iam.gserviceaccount.com'), specs)
        self.assertNotIn('roles/owner', repr(specs))
        self.assertNotIn('roles/editor', repr(specs))

    def test_execute_flags_rejected_outside_matching_operation(self):
        self.assertEqual(manage_main(['--mode=validate', '--execute-dataflow']), 1)
        self.assertEqual(manage_main(['--mode=deploy', '--execute-stop']), 1)

    def test_preview_never_applies_iam_or_launches_job(self):
        with patch('pipelines.streaming.manage.preflight', return_value=[]), \
             patch('pipelines.streaming.manage.reconcile_iam', return_value=[('project',)] ) as iam, \
             patch('pipelines.streaming.manage.launch') as launch:
            from pipelines.streaming.manage import manage
            manage(self.config, self.resources, self.manifest, 'deploy')
        iam.assert_called_once_with(self.config, self.resources, self.manifest, apply=False)
        launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
