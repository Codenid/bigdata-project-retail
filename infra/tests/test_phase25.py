import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from infra.config.settings import ROOT, load
from infra.bigquery.manage import APIError, manage, without_new_owner


class FakeAPI:
    def __init__(self, fixture, bootstrap):
        self.f = fixture
        self.bootstrap = bootstrap

    def project_permissions(self, permissions):
        return permissions if self.f.admin else []

    def request(self, method, path, body=None, query=None, etag=None):
        self.f.calls.append((self.bootstrap, method, path, copy.deepcopy(body), query))
        if '/jobs' in path:
            raise AssertionError('No se permiten jobs')
        if method == 'GET':
            if path.endswith(('/tables', '/models', '/routines')):
                kind = path.split('/')[-1]
                return {kind: [{}]} if self.f.child == kind else {}
            if self.f.dataset is None:
                raise APIError(404, 'Not found')
            return copy.deepcopy(self.f.dataset)
        if method == 'POST':
            self.f.mutations.append(method)
            if self.f.collision:
                raise APIError(409, 'Already exists')
            self.assert_create_body(body)
            self.f.dataset = copy.deepcopy(body)
            self.f.dataset['etag'] = 'v1'
            if self.f.auto_owner:
                self.f.dataset['access'].append({'role': 'OWNER', 'userByEmail': self.f.email})
            return copy.deepcopy(self.f.dataset)
        if method == 'PATCH':
            self.f.mutations.append(method)
            if not self.f.dataset:
                raise APIError(404, 'Not found')
            if etag != self.f.dataset['etag']:
                raise APIError(412, 'Precondition failed')
            if 'access' in body and not any(e.get('userByEmail') == self.f.email for e in body['access']):
                if not self.f.admin:
                    raise AssertionError('No se debe retirar owner sin prueba de administración')
                if self.f.fail_cleanup:
                    raise RuntimeError('cleanup denied')
            if self.f.fail_metadata and 'access' not in body:
                raise RuntimeError('metadata failed')
            self.f.dataset.update(copy.deepcopy(body))
            self.f.dataset['etag'] += 'x'
            return copy.deepcopy(self.f.dataset)
        if method == 'DELETE':
            if query != {'deleteContents': 'false'}:
                raise AssertionError('Delete recursivo prohibido')
            self.f.mutations.append(method)
            self.f.dataset = None
            return {}
        raise AssertionError((method, path))

    def assert_create_body(self, body):
        for field in ('defaultTableExpirationMs', 'defaultPartitionExpirationMs', 'storageBillingModel'):
            if field in body:
                raise AssertionError('Propiedad no aprobada en insert: ' + field)


class Phase25(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        text = (ROOT / 'config/dev.env.example').read_text()
        for key, value in {'GCP_PROJECT_ID': 'retailsmart-test', 'GCP_REGION': 'us-central1',
                           'GCP_LOCATION': 'us-central1', 'RESOURCE_SUFFIX': 'test',
                           'BOOTSTRAP_ACCOUNT': 'bootstrap@example.com'}.items():
            text = text.replace(key + '=\n', key + '=' + value + '\n')
        path = Path(self.tmp.name) / 'test.env'
        path.write_text(text)
        self.config, self.resources = load(path)
        self.manifest = json.loads((ROOT / 'infra/config/bigquery.json').read_text())
        self.email = self.config['DEPLOYER_SERVICE_ACCOUNT_ID'] + '@retailsmart-test.iam.gserviceaccount.com'
        self.dataset = None
        self.policy = {'bindings': []}
        self.calls, self.mutations, self.iam_calls = [], [], []
        self.admin, self.auto_owner = True, False
        self.fail_cleanup, self.fail_metadata, self.collision = False, False, False
        self.child = None

    def cloud(self, config, *args):
        if args[:2] == ('services', 'list'):
            return [{'config': {'name': self.manifest['api']}}]
        if args[:3] == ('iam', 'roles', 'describe'):
            return {'includedPermissions': self.manifest['creation_permissions'] + self.manifest['dataset_permissions']}
        if args[:2] == ('projects', 'get-iam-policy'):
            return copy.deepcopy(self.policy)
        binding = {'role': self.manifest['creation_role'], 'members': ['serviceAccount:' + self.email]}
        self.iam_calls.append(args)
        if args[:2] == ('projects', 'add-iam-policy-binding'):
            self.policy['bindings'].append(binding)
        elif args[:2] == ('projects', 'remove-iam-policy-binding'):
            self.policy['bindings'].remove(binding)
        else:
            raise AssertionError(args)
        return self.policy

    def execute(self, mode, **kwargs):
        def factory(config, manifest, impersonation=None):
            return FakeAPI(self, impersonation is None)
        with patch('infra.bigquery.manage.run', side_effect=self.cloud), \
                patch('infra.bigquery.manage.BigQueryAPI', side_effect=factory):
            return manage(self.config, self.resources, self.manifest, mode, **kwargs)

    def test_create_validate_repeat_and_no_expiration_or_billing_configuration(self):
        first = self.execute('deploy')
        self.assertEqual(first['changes'], 1)
        self.assertTrue(first['temporary_dataset_access_removed'])
        self.assertTrue(first['temporary_project_access_removed'])
        self.assertFalse(self.policy['bindings'])
        self.assertFalse(any(e.get('userByEmail') == self.email for e in self.dataset['access']))
        self.assertEqual(self.execute('validate')['changes'], 0)
        self.assertEqual(self.execute('deploy')['changes'], 0)
        for _, method, _, body, _ in self.calls:
            if method in ('POST', 'PATCH'):
                self.assertNotIn('storageBillingModel', body)

    def test_automatic_creator_owner_detected_and_removed(self):
        self.auto_owner = True
        result = self.execute('deploy')
        self.assertTrue(result['automatic_creator_owner_detected'])
        self.assertTrue(result['temporary_dataset_access_removed'])
        self.assertFalse(any(e.get('userByEmail') == self.email for e in self.dataset['access']))
        self.assertEqual(result['dataset_iam_changes'], 1)

    def test_preexisting_accesses_are_preserved(self):
        self.execute('deploy')
        entry = {'role': 'OWNER', 'userByEmail': self.email}
        other = {'role': 'READER', 'groupByEmail': 'team@example.com'}
        self.dataset['access'] += [entry, other]
        before = copy.deepcopy(self.dataset['access'])
        self.policy['bindings'].append({'role': self.manifest['creation_role'], 'members': ['serviceAccount:' + self.email]})
        result = self.execute('deploy')
        self.assertEqual(self.dataset['access'], before)
        self.assertTrue(result['preexisting_dataset_owner'])
        self.assertEqual(result['project_iam_changes'], 0)
        self.assertEqual(result['dataset_iam_changes'], 0)
        self.assertTrue(self.policy['bindings'])

    def test_bootstrap_without_admin_stops_before_mutations(self):
        self.admin = False
        with self.assertRaisesRegex(RuntimeError, 'Bootstrap sin administración'):
            self.execute('deploy')
        self.assertFalse(self.mutations)
        self.assertFalse(self.iam_calls)

    def test_cleanup_rechecks_admin_and_does_not_remove_owner_on_loss(self):
        self.auto_owner = True
        original = FakeAPI.request
        def lost_admin(api, method, path, body=None, query=None, etag=None):
            result = original(api, method, path, body, query, etag)
            if method == 'POST':
                self.admin = False
            return result
        with patch.object(FakeAPI, 'request', new=lost_admin):
            with self.assertRaisesRegex(RuntimeError, 'ERROR DE LIMPIEZA'):
                self.execute('deploy')
        self.assertTrue(any(e.get('userByEmail') == self.email for e in self.dataset['access']))
        self.assertFalse(self.policy['bindings'])  # cleanup proyecto se intenta incluso si falla ACL

    def test_cleanup_failure_reported_and_project_role_removed(self):
        self.fail_cleanup = True
        with self.assertRaisesRegex(RuntimeError, 'ERROR DE LIMPIEZA'):
            self.execute('deploy')
        self.assertFalse(self.policy['bindings'])

    def test_metadata_failure_does_not_leak_temporary_access(self):
        self.execute('deploy')
        self.dataset['labels'].pop('layer')
        self.fail_metadata = True
        with self.assertRaisesRegex(RuntimeError, 'metadata failed'):
            self.execute('deploy')
        self.assertFalse(any(e.get('userByEmail') == self.email for e in self.dataset['access']))

    def test_expiration_drift_cleared_only_in_deploy(self):
        self.execute('deploy')
        self.dataset['defaultTableExpirationMs'] = '86400000'
        self.dataset['defaultPartitionExpirationMs'] = '86400000'
        with self.assertRaisesRegex(RuntimeError, 'drift'):
            self.execute('validate')
        self.assertEqual(self.execute('deploy')['changes'], 1)
        self.assertIsNone(self.dataset['defaultTableExpirationMs'])
        self.assertIsNone(self.dataset['defaultPartitionExpirationMs'])

    def test_nonempty_dataset_blocks_all_operations(self):
        self.execute('deploy')
        count = len(self.mutations)
        for kind in ('tables', 'models', 'routines'):
            self.child = kind
            for mode in ('deploy', 'validate', 'destroy'):
                with self.assertRaisesRegex(RuntimeError, 'contiene artefactos'):
                    self.execute(mode, execute_destroy=mode == 'destroy')
        self.assertEqual(len(self.mutations), count)

    def test_destroy_preview_then_empty_destroy_and_recreate(self):
        self.execute('deploy')
        self.assertEqual(self.execute('destroy')['changes'], 0)
        self.assertIsNotNone(self.dataset)
        self.assertEqual(self.execute('destroy', execute_destroy=True)['changes'], 1)
        self.assertIsNone(self.dataset)
        self.assertEqual(self.execute('destroy', execute_destroy=True)['changes'], 0)
        self.assertEqual(self.execute('deploy')['changes'], 1)

    def test_wrong_location_or_ownership_never_adopted(self):
        self.execute('deploy')
        self.dataset['location'] = 'US'
        with self.assertRaisesRegex(RuntimeError, 'Location incompatible'):
            self.execute('deploy')
        self.dataset['location'] = 'us-central1'
        self.dataset['labels'].pop('component_id')
        with self.assertRaisesRegex(RuntimeError, 'pertenencia'):
            self.execute('deploy')

    def test_403_is_not_treated_as_missing(self):
        with patch.object(FakeAPI, 'request', side_effect=APIError(403, 'denied')):
            with self.assertRaises(APIError):
                self.execute('deploy')
        self.assertFalse(self.mutations)
        self.assertFalse(self.iam_calls)

    def test_invalid_expiration_manifest_stops_before_cloud(self):
        self.manifest['dataset_defaults']['defaultTableExpirationMs'] = '1000'
        with self.assertRaises(ValueError):
            self.execute('deploy')
        self.assertFalse(self.calls)
        self.assertFalse(self.iam_calls)

    def test_conditional_and_unrelated_acl_entries_preserved(self):
        baseline = [{'role': 'OWNER', 'userByEmail': self.email, 'condition': {'expression': 'true'}}]
        added = {'role': self.manifest['dataset_role'], 'userByEmail': self.email}
        other = {'role': 'READER', 'groupByEmail': 'team@example.com'}
        self.assertEqual(without_new_owner(baseline + [added, other], baseline, self.email, self.manifest), baseline + [other])

    def test_owner_iam_member_representation_is_detected_and_baseline_preserved(self):
        initial = {'role': 'OWNER', 'userByEmail': self.email}
        equivalent = {'role': self.manifest['dataset_role'], 'iamMember': 'serviceAccount:' + self.email}
        self.assertEqual(without_new_owner([equivalent], [initial], self.email, self.manifest), [equivalent])
        self.assertEqual(without_new_owner([equivalent], [], self.email, self.manifest), [])

    def test_collision_does_not_adopt_or_change_foreign_acl(self):
        self.collision = True
        with self.assertRaises(APIError):
            self.execute('deploy')
        self.assertIsNone(self.dataset)
        self.assertFalse(self.policy['bindings'])

    def test_runtime_and_public_access_rejected(self):
        self.execute('deploy')
        self.dataset['access'].append({'role': 'READER', 'specialGroup': 'allAuthenticatedUsers'})
        with self.assertRaisesRegex(RuntimeError, 'público'):
            self.execute('validate')
        self.dataset['access'][-1] = {'role': 'WRITER', 'userByEmail':
            self.config['DATAFLOW_SERVICE_ACCOUNT_ID'] + '@retailsmart-test.iam.gserviceaccount.com'}
        with self.assertRaisesRegex(RuntimeError, 'Runtime BigQuery'):
            self.execute('validate')
