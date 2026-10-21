import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from infra.config.settings import ROOT, load
from infra.storage.manage import manage


class Phase24(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        text = (ROOT / 'config/dev.env.example').read_text()
        for key, value in {'GCP_PROJECT_ID': 'retailsmart-test', 'GCP_REGION': 'us-central1',
                           'GCP_LOCATION': 'us-central1', 'RESOURCE_SUFFIX': 'test',
                           'BOOTSTRAP_ACCOUNT': 'test@example.com'}.items():
            text = text.replace(key + '=\n', key + '=' + value + '\n')
        path = Path(self.tmp.name) / 'test.env'
        path.write_text(text)
        self.config, self.resources = load(path)
        self.manifest = json.loads((ROOT / 'infra/config/storage.json').read_text())
        self.buckets, self.objects, self.policy = {}, {}, {'bindings': []}
        self.api_policies, self.mutations, self.iam_calls = {}, [], []
        self.member = 'serviceAccount:' + self.config['DEPLOYER_SERVICE_ACCOUNT_ID'] + '@retailsmart-test.iam.gserviceaccount.com'

    def cloud(self, config, *args):
        if args[:2] == ('services', 'list'):
            return [{'config': {'name': self.manifest['api']}}]
        if args[:3] == ('iam', 'roles', 'describe'):
            return {'includedPermissions': self.manifest['required_permissions']}
        if args[:2] == ('projects', 'describe'):
            return {'projectId': config['GCP_PROJECT_ID'], 'projectNumber': '123', 'lifecycleState': 'ACTIVE'}
        if args[:2] == ('projects', 'get-iam-policy'):
            return copy.deepcopy(self.policy)
        self.iam_calls.append(args)
        binding = {'role': self.manifest['deployer_role'], 'members': [self.member]}
        if args[:2] == ('projects', 'add-iam-policy-binding'):
            self.policy['bindings'].append(binding)
        elif args[:2] == ('projects', 'remove-iam-policy-binding'):
            self.policy['bindings'].remove(binding)
        else:
            raise AssertionError(args)
        return self.policy

    def request(self, method, path, body=None, query=None):
        if method == 'GET' and path.endswith('/iam'):
            return self.api_policies.get(path.split('/')[1], {'bindings': []})
        self.mutations.append((method, path, copy.deepcopy(body), query))
        if method == 'POST':
            if body['name'] in self.buckets:
                raise RuntimeError('Cloud Storage HTTP 409: colisión global')
            record = copy.deepcopy(body)
            record.update(projectNumber='123', locationType='region', metageneration='1')
            self.buckets[body['name']] = record
        elif method == 'PATCH':
            bucket = self.buckets[path.split('/')[1]]
            self.assertEqual(query['ifMetagenerationMatch'], bucket['metageneration'])
            bucket.update(copy.deepcopy(body))
        elif method == 'DELETE' and '/o/' in path:
            bucket = path.split('/')[1]
            self.objects[bucket] = []
        elif method == 'DELETE':
            bucket = path.split('/')[1]
            if self.objects.get(bucket):
                raise RuntimeError('Bucket no vacío')
            del self.buckets[bucket]
        else:
            raise AssertionError((method, path))
        return {}

    def items(self, path, query):
        if path == 'b':
            return iter(copy.deepcopy(list(self.buckets.values())))
        return iter(copy.deepcopy(self.objects.get(path.split('/')[1], [])))

    def execute(self, mode, **kwargs):
        with patch('infra.storage.manage.run', side_effect=self.cloud), \
                patch('infra.storage.manage.StorageAPI') as api:
            api.return_value.request.side_effect = self.request
            api.return_value.items.side_effect = self.items
            return manage(self.config, self.resources, self.manifest, mode, **kwargs)

    def test_deploy_validate_repeat_and_properties(self):
        first = self.execute('deploy')
        self.assertEqual(first['changes'], 3)
        self.assertEqual(first['iam_changes'], 2)
        self.assertTrue(first['temporary_binding_removed'])
        self.assertFalse(self.policy['bindings'])
        self.assertEqual(self.execute('validate')['changes'], 0)
        self.assertEqual(self.execute('deploy')['changes'], 0)
        self.assertEqual(len(self.buckets), 3)
        bronze = self.buckets[self.resources['RS-DATA-001']['name']]
        silver = self.buckets[self.resources['RS-DATA-002']['name']]
        technical = self.buckets[self.resources['RS-STR-004']['name']]
        self.assertEqual(bronze['softDeletePolicy']['retentionDurationSeconds'], '604800')
        self.assertEqual(silver['softDeletePolicy']['retentionDurationSeconds'], '0')
        self.assertEqual(technical['softDeletePolicy']['retentionDurationSeconds'], '0')
        self.assertEqual(technical['lifecycle']['rule'], [{'action': {'type': 'Delete'}, 'condition': {'age': 1}}])
        self.assertEqual(bronze['lifecycle']['rule'], [])
        self.assertEqual(silver['lifecycle']['rule'], [])
        self.assertNotIn('encryption', bronze)

    def test_preexisting_binding_is_not_removed(self):
        binding = {'role': self.manifest['deployer_role'], 'members': [self.member]}
        self.policy['bindings'].append(binding)
        result = self.execute('deploy')
        self.assertEqual(result['iam_changes'], 0)
        self.assertEqual(self.policy['bindings'], [binding])
        self.assertFalse(self.iam_calls)

    def test_cleanup_on_partial_creation_failure_and_resume(self):
        original = self.request
        def failed(method, path, body=None, query=None):
            if method == 'POST' and body['name'] == self.resources['RS-DATA-002']['name']:
                raise RuntimeError('Fallo en creación')
            return original(method, path, body, query)
        with patch('infra.storage.manage.run', side_effect=self.cloud), \
                patch('infra.storage.manage.StorageAPI') as api:
            api.return_value.items.side_effect = self.items
            api.return_value.request.side_effect = failed
            with self.assertRaisesRegex(RuntimeError, 'Fallo en creación'):
                manage(self.config, self.resources, self.manifest, 'deploy')
        self.assertFalse(self.policy['bindings'])
        self.assertEqual(len(self.buckets), 1)
        self.assertEqual(self.execute('deploy')['changes'], 2)

    def test_cleanup_when_token_creation_fails(self):
        with patch('infra.storage.manage.run', side_effect=self.cloud), \
                patch('infra.storage.manage.StorageAPI', side_effect=RuntimeError('token denied')):
            with self.assertRaisesRegex(RuntimeError, 'token denied'):
                manage(self.config, self.resources, self.manifest, 'deploy')
        self.assertFalse(self.policy['bindings'])

    def test_cleanup_failure_is_not_hidden(self):
        original = self.cloud
        def failed(config, *args):
            if args[:2] == ('projects', 'remove-iam-policy-binding'):
                raise RuntimeError('remove denied')
            return original(config, *args)
        with patch('infra.storage.manage.run', side_effect=failed), \
                patch('infra.storage.manage.StorageAPI') as api:
            api.return_value.items.side_effect = self.items
            api.return_value.request.side_effect = self.request
            with self.assertRaisesRegex(RuntimeError, 'ERROR DE LIMPIEZA IAM'):
                manage(self.config, self.resources, self.manifest, 'deploy')

    def test_validate_absent_does_not_create(self):
        with self.assertRaisesRegex(RuntimeError, 'ausentes o con drift'):
            self.execute('validate')
        self.assertFalse(self.mutations)
        self.assertFalse(self.policy['bindings'])

    def test_unowned_bucket_blocks_all_resource_mutations(self):
        self.execute('deploy')
        next(iter(self.buckets.values()))['labels'].pop('component_id')
        count = len(self.mutations)
        with self.assertRaisesRegex(RuntimeError, 'pertenencia'):
            self.execute('deploy')
        self.assertEqual(len(self.mutations), count)
        self.assertFalse(self.policy['bindings'])

    def test_other_project_and_location_are_rejected(self):
        self.execute('deploy')
        first = next(iter(self.buckets.values()))
        first['projectNumber'] = '999'
        with self.assertRaisesRegex(RuntimeError, 'otro proyecto'):
            self.execute('deploy')
        first['projectNumber'] = '123'
        first['location'] = 'EU'
        with self.assertRaisesRegex(RuntimeError, 'Location incompatible'):
            self.execute('deploy')

    def test_locked_retention_not_cleared(self):
        self.execute('deploy')
        next(iter(self.buckets.values()))['retentionPolicy'] = {'isLocked': True}
        with self.assertRaisesRegex(RuntimeError, 'retentionPolicy'):
            self.execute('deploy')

    def test_drift_and_metageneration_guard(self):
        self.execute('deploy')
        next(iter(self.buckets.values()))['softDeletePolicy']['retentionDurationSeconds'] = '0'
        with self.assertRaisesRegex(RuntimeError, 'drift'):
            self.execute('validate')
        self.assertEqual(self.execute('deploy')['changes'], 1)
        self.assertEqual(self.execute('validate')['changes'], 0)

    def test_destroy_preview_empty_destroy_recreate(self):
        self.execute('deploy')
        count = len(self.mutations)
        self.assertEqual(self.execute('destroy')['changes'], 0)
        self.assertEqual(len(self.mutations), count)
        self.assertEqual(self.execute('destroy', execute_destroy=True)['changes'], 3)
        self.assertEqual(self.execute('destroy', execute_destroy=True)['changes'], 0)
        self.assertEqual(self.execute('deploy')['changes'], 3)

    def test_destroy_nonempty_requires_explicit_purge(self):
        self.execute('deploy')
        name = self.resources['RS-DATA-002']['name']
        self.objects[name] = [{'name': 'test', 'generation': '1'}]
        count = len(self.mutations)
        with self.assertRaisesRegex(RuntimeError, 'requiere --purge'):
            self.execute('destroy', execute_destroy=True)
        self.assertEqual(len(self.mutations), count)
        self.assertFalse(self.policy['bindings'])
        self.assertEqual(self.execute('destroy', execute_destroy=True, purge=True)['changes'], 3)

    def test_public_and_runtime_bindings_are_rejected(self):
        self.execute('deploy')
        name = self.resources['RS-DATA-001']['name']
        self.api_policies[name] = {'bindings': [{'role': 'roles/storage.objectViewer', 'members': ['allUsers']}]}
        with self.assertRaisesRegex(RuntimeError, 'público'):
            self.execute('validate')
        self.api_policies[name]['bindings'][0]['members'] = [
            'serviceAccount:' + self.config['DATAFLOW_SERVICE_ACCOUNT_ID'] + '@retailsmart-test.iam.gserviceaccount.com']
        with self.assertRaisesRegex(RuntimeError, 'Runtime Storage'):
            self.execute('validate')

    def test_missing_configuration_stops_before_iam(self):
        del self.config['STORAGE_CLASS']
        with self.assertRaises(ValueError):
            self.execute('deploy')
        self.assertFalse(self.iam_calls)

    def test_permission_error_never_means_missing(self):
        with patch('infra.storage.manage.run', side_effect=RuntimeError('PERMISSION_DENIED')):
            with self.assertRaises(RuntimeError):
                manage(self.config, self.resources, self.manifest, 'deploy')
        self.assertFalse(self.mutations)
