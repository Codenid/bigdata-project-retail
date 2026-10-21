"""Orquestación: orden, fallos, previews y aislamiento IAM."""
import io
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

from infra.streaming_core.manage import orchestrate, normalize


class Phase26(unittest.TestCase):
    def execute(self, mode='deploy', execute=False, failure=None, changes=0):
        self.calls = []
        def module(name):
            def call(*args, **kwargs):
                operation = args[3]
                self.calls.append((name, operation, kwargs))
                if name == failure:
                    raise RuntimeError('fallo simulado')
                return {'changes': changes if operation == 'deploy' else 0, 'iam_changes': 2}
            return call
        def bootstrap(*args, **kwargs):
            self.calls.append(('bootstrap', kwargs['apply'], {}))
            if failure == 'bootstrap':
                raise RuntimeError('bootstrap falló')
            return {'changes': 0}
        self.output = io.StringIO()
        self.errors = io.StringIO()
        with patch('infra.streaming_core.manage.load', return_value=({}, {})), \
             patch('infra.streaming_core.manage.manifest', side_effect=lambda name:
                   ['pubsub.googleapis.com'] if name == 'apis' else {}), \
             patch('infra.streaming_core.manage.apis.bootstrap', side_effect=bootstrap), \
             patch('infra.streaming_core.manage.iam.manage', side_effect=module('iam')), \
             patch('infra.streaming_core.manage.pubsub.manage', side_effect=module('pubsub')), \
             patch('infra.streaming_core.manage.storage.manage', side_effect=module('storage')), \
             patch('infra.streaming_core.manage.bigquery.manage', side_effect=module('bigquery')), \
             redirect_stdout(self.output), redirect_stderr(self.errors):
            return orchestrate(mode, 'test.env', execute)

    def test_deploy_order(self):
        self.assertEqual(self.execute(), 0)
        self.assertEqual([c[0] for c in self.calls], ['bootstrap', 'iam', 'pubsub', 'storage', 'bigquery'])
        self.assertTrue(self.calls[0][1])

    def test_validate_never_deploys(self):
        self.assertEqual(self.execute('validate'), 0)
        self.assertFalse(self.calls[0][1])
        self.assertTrue(all(c[1] == 'validate' for c in self.calls[1:]))

    def test_fail_fast_and_skip(self):
        self.assertEqual(self.execute(failure='pubsub'), 1)
        self.assertEqual([c[0] for c in self.calls], ['bootstrap', 'iam', 'pubsub'])
        self.assertIn('[SKIP] Storage', self.output.getvalue())
        self.assertIn('[SKIP] BigQuery', self.output.getvalue())
        self.assertIn('fallo simulado', self.errors.getvalue())

    def test_bootstrap_failure_blocks_iam(self):
        self.assertEqual(self.execute(failure='bootstrap'), 1)
        self.assertEqual(len(self.calls), 1)

    def test_preview_default_keeps_foundation(self):
        self.assertEqual(self.execute('destroy'), 0)
        self.assertEqual([c[0] for c in self.calls], ['bootstrap', 'iam', 'bigquery', 'storage', 'pubsub'])
        self.assertEqual(self.calls[1][1], 'validate')
        self.assertTrue(all(c[1] == 'destroy' and not c[2] for c in self.calls[2:]))

    def test_all_prechecks_before_first_delete_and_reverse_order(self):
        self.assertEqual(self.execute('destroy', True), 0)
        self.assertEqual([c[0] for c in self.calls[2:]],
                         ['bigquery', 'storage', 'pubsub', 'bigquery', 'storage', 'pubsub'])
        self.assertTrue(all(not c[2] for c in self.calls[2:5]))
        self.assertTrue(all(c[2] == {'execute_destroy': True} for c in self.calls[5:]))

    def test_precheck_failure_prevents_every_delete(self):
        self.assertEqual(self.execute('destroy', True, failure='storage'), 1)
        self.assertFalse(any(c[2].get('execute_destroy') for c in self.calls))

    def test_zero_permanent_changes_separate_from_iam(self):
        self.assertEqual(self.execute(), 0)
        self.assertIn('changes=0 iam_changes=8', self.output.getvalue())

    def test_bigquery_iam_metrics(self):
        self.assertEqual(normalize({'changes': 0, 'project_iam_changes': 2,
                                    'dataset_iam_changes': 2})['iam_changes'], 4)

    def test_configuration_failure_blocks_cloud(self):
        with patch('infra.streaming_core.manage.load', side_effect=ValueError('config inválida')), \
             patch('infra.streaming_core.manage.apis.bootstrap') as cloud, \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(orchestrate('deploy', 'bad.env'), 1)
        cloud.assert_not_called()

    def test_destructive_flag_rejected_for_deploy(self):
        with self.assertRaises(ValueError):
            orchestrate('deploy', 'test.env', True)

    def test_failed_module_counts_are_explicitly_incomplete(self):
        self.execute(failure='storage')
        self.assertIn('"counts_complete": false', self.output.getvalue())
        self.assertIn('Conteos parciales', self.output.getvalue())

    def test_forward_config_and_resources_without_reinterpretation(self):
        config, resources = {'external': 'value'}, {'catalog': 'inventory'}
        with patch('infra.streaming_core.manage.load', return_value=(config, resources)),              patch('infra.streaming_core.manage.manifest', side_effect=lambda name:
                   ['pubsub.googleapis.com'] if name == 'apis' else {}),              patch('infra.streaming_core.manage.apis.bootstrap', return_value={'changes': 0}),              patch('infra.streaming_core.manage.iam.manage', side_effect=RuntimeError('stop')) as identity,              redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            orchestrate('deploy', 'external.env')
        self.assertIs(identity.call_args.args[0], config)
        self.assertIs(identity.call_args.args[1], resources)
