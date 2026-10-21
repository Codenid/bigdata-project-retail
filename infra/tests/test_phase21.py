import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from infra.config.settings import ROOT, load
from infra.bootstrap.apis import bootstrap, run


class Phase21(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'test.env'
        text = (ROOT / 'config/dev.env.example').read_text()
        for key, value in {'GCP_PROJECT_ID': 'test-retailsmart', 'GCP_REGION': 'us-central1',
                           'GCP_LOCATION': 'us-central1', 'RESOURCE_SUFFIX': 'localtest',
                           'BOOTSTRAP_ACCOUNT': 'tester@example.com'}.items():
            text = text.replace(key + '=\n', key + '=' + value + '\n')
        self.path.write_text(text)

    def test_catalog_and_labels(self):
        config, resources = load(self.path)
        self.assertEqual(len(resources), 9)
        self.assertEqual(resources['RS-STR-001']['labels']['vertical'], 'multi')
        self.assertNotIn('layer', resources['RS-STR-001']['labels'])
        self.assertEqual(resources['RS-DATA-001']['labels']['layer'], 'bronze')
        self.assertTrue(config['BRONZE_BUCKET'].endswith('-localtest'))

    def test_reject_uncataloged_name(self):
        self.path.write_text(self.path.read_text().replace('rs-dev-str-ps-events\n', 'other-topic\n'))
        with self.assertRaises(ValueError):
            load(self.path)

    def test_reject_missing_project(self):
        self.path.write_text(self.path.read_text().replace('test-retailsmart', ''))
        with self.assertRaises(ValueError):
            load(self.path)

    def test_session_project_and_region(self):
        config, _ = load(self.path)
        with patch('infra.bootstrap.apis.subprocess.run') as process:
            process.return_value.returncode = 0
            process.return_value.stderr = ''
            process.return_value.stdout = '{}'
            run(config, 'projects', 'describe', config['GCP_PROJECT_ID'])
            args, kwargs = process.call_args
            self.assertEqual(kwargs['env']['CLOUDSDK_CORE_PROJECT'], config['GCP_PROJECT_ID'])
            self.assertEqual(kwargs['env']['CLOUDSDK_COMPUTE_REGION'], config['GCP_REGION'])
            self.assertIn('--account', args[0])

    def test_project_id_alias(self):
        self.path.write_text(self.path.read_text().replace('GCP_PROJECT_ID=', 'PROJECT_ID='))
        config, _ = load(self.path)
        self.assertEqual(config['GCP_PROJECT_ID'], 'test-retailsmart')

    @patch('infra.bootstrap.apis.shutil.which', return_value='/fake/gcloud')
    def test_inactive_account_stops_before_project(self, _):
        config, _ = load(self.path)
        with patch('infra.bootstrap.apis.run', return_value=[]) as command:
            with self.assertRaises(RuntimeError):
                bootstrap(config, ['one.googleapis.com'], apply=True)
            self.assertEqual(command.call_count, 1)

    @patch('infra.bootstrap.apis.shutil.which', return_value='/fake/gcloud')
    def test_deploy_only_missing_and_repeat(self, _):
        config, _resources = load(self.path)
        enabled = {'one.googleapis.com'}
        calls = []
        def fake(_config, *args):
            calls.append(args)
            if args[:2] == ('auth', 'list'):
                return [{'account': config['BOOTSTRAP_ACCOUNT'], 'status': 'ACTIVE'}]
            if args[:2] == ('projects', 'describe'):
                return {'projectId': config['GCP_PROJECT_ID'], 'lifecycleState': 'ACTIVE'}
            if args[0] == 'billing':
                return {'billingEnabled': True}
            if args[:2] == ('services', 'enable'):
                enabled.update(args[2:])
                return None
            return [{'config': {'name': name}} for name in enabled]
        with patch('infra.bootstrap.apis.run', side_effect=fake):
            for _ in range(2):
                bootstrap(config, ['one.googleapis.com', 'two.googleapis.com'], apply=True)
        self.assertEqual([args for args in calls if args[:2] == ('services', 'enable')],
                         [('services', 'enable', 'two.googleapis.com')])

    @patch('infra.bootstrap.apis.shutil.which', return_value='/fake/gcloud')
    def test_billing_failure_stops_mutations(self, _):
        config, _resources = load(self.path)
        with patch('infra.bootstrap.apis.run', side_effect=[
                [{'account': config['BOOTSTRAP_ACCOUNT'], 'status': 'ACTIVE'}],
                {'projectId': config['GCP_PROJECT_ID'], 'lifecycleState': 'ACTIVE'},
                {'billingEnabled': False}]) as command:
            with self.assertRaises(RuntimeError):
                bootstrap(config, ['one.googleapis.com'], apply=True)
            self.assertEqual(command.call_count, 3)

    @patch('infra.bootstrap.apis.shutil.which', return_value='/fake/gcloud')
    def test_validate_never_enables(self, _):
        config, _resources = load(self.path)
        with patch('infra.bootstrap.apis.run', side_effect=[
                [{'account': config['BOOTSTRAP_ACCOUNT'], 'status': 'ACTIVE'}],
                {'projectId': config['GCP_PROJECT_ID'], 'lifecycleState': 'ACTIVE'},
                {'billingEnabled': True}, []]) as command:
            with self.assertRaises(RuntimeError):
                bootstrap(config, ['one.googleapis.com'])
            self.assertEqual(command.call_count, 4)


if __name__ == '__main__':
    unittest.main()
