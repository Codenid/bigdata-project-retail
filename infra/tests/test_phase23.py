import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from infra.config.settings import ROOT, load
from infra.pubsub.manage import manage


class Phase23(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        text = (ROOT / 'config/dev.env.example').read_text()
        for key, value in {'GCP_PROJECT_ID': 'academic-test', 'GCP_REGION': 'us-central1',
                           'GCP_LOCATION': 'us-central1', 'RESOURCE_SUFFIX': 'test',
                           'BOOTSTRAP_ACCOUNT': 'test@example.com'}.items():
            text = text.replace(key + '=\n', key + '=' + value + '\n')
        path = Path(self.tmp.name) / 'test.env'
        path.write_text(text)
        self.config, self.resources = load(path)
        self.manifest = json.loads((ROOT / 'infra/config/pubsub.json').read_text())
        self.topics, self.subs, self.policy = {}, {}, {}
        self.calls, self.mutations = [], []

    def fake(self, config, *args):
        self.calls.append(args)
        if args[:2] == ('services', 'list'):
            return [{'config': {'name': self.manifest['api']}}]
        if args[:3] == ('iam', 'roles', 'describe'):
            return {'includedPermissions': self.manifest['required_permissions']}
        if args[:2] == ('projects', 'get-iam-policy'):
            return copy.deepcopy(self.policy)
        if args[:2] == ('projects', 'add-iam-policy-binding'):
            self.policy = {'bindings': [{'role': self.manifest['deployer_role'], 'members': [
                'serviceAccount:' + self.config['DEPLOYER_SERVICE_ACCOUNT_ID'] + '@academic-test.iam.gserviceaccount.com']}]}
            return self.policy
        if args[:2] == ('projects', 'remove-iam-policy-binding'):
            self.policy = {}
            return {}
        self.assertEqual(args[0], 'pubsub')
        self.assertNotIn('message-storage', repr(args))
        records = self.topics if args[1] == 'topics' else self.subs
        if args[2] == 'list':
            return copy.deepcopy(list(records.values()))
        if args[2] == 'list-subscriptions':
            return ['https://pubsub.googleapis.com/v1/' + sub['name']
                    for sub in self.subs.values() if sub.get('topic') == args[3]]
        self.mutations.append(args)
        name = args[3]
        if args[2] == 'delete':
            del records[name]
            return {}
        record = records.setdefault(name, {'name': name})
        for arg in args[4:]:
            if arg.startswith(('--labels=', '--update-labels=')):
                record.setdefault('labels', {}).update(dict(pair.split('=', 1) for pair in arg.split('=', 1)[1].split(',')))
            elif arg.startswith('--topic='):
                record['topic'] = arg.split('=', 1)[1]
            elif arg.startswith('--ack-deadline='):
                record['ackDeadlineSeconds'] = int(arg.split('=', 1)[1])
            elif arg.startswith('--message-retention-duration='):
                record['messageRetentionDuration'] = arg.split('=', 1)[1]
            elif arg.startswith('--expiration-period='):
                record['expirationPolicy'] = {'ttl': arg.split('=', 1)[1]}
            elif arg == '--no-retain-acked-messages':
                record['retainAckedMessages'] = False
            elif arg == '--clear-retry-policy':
                record.pop('retryPolicy', None)
        return copy.deepcopy(record)

    def execute(self, mode, **kwargs):
        with patch('infra.pubsub.manage.run', side_effect=self.fake):
            return manage(self.config, self.resources, self.manifest, mode, **kwargs)['changes']

    def test_deploy_validate_repeat_destroy_recreate(self):
        self.assertEqual(self.execute('deploy'), 3)  # three resources; IAM contabilizado por separado
        self.assertEqual(self.execute('validate'), 0)
        self.assertEqual(self.execute('deploy'), 0)
        count = len(self.mutations)
        self.assertEqual(self.execute('destroy'), 0)  # preview only
        self.assertEqual(len(self.mutations), count)
        self.assertEqual(self.execute('destroy', execute_destroy=True), 3)
        self.assertEqual(self.execute('destroy', execute_destroy=True), 0)
        self.assertEqual(self.execute('deploy'), 3)

    def test_validate_missing_resources_cleans_temporary_binding(self):
        with self.assertRaisesRegex(RuntimeError, 'Recursos ausentes'):
            self.execute('validate')
        self.assertFalse(self.mutations)

    def test_access_denied_not_absence(self):
        with patch('infra.pubsub.manage.run', side_effect=RuntimeError('PERMISSION_DENIED')):
            with self.assertRaises(RuntimeError):
                manage(self.config, self.resources, self.manifest, 'deploy')
        self.assertFalse(self.mutations)

    def test_subscription_misrouting_blocks_changes(self):
        self.execute('deploy')
        sub = next(iter(self.subs.values()))
        sub['topic'] = 'projects/academic-test/topics/other'
        count = len(self.mutations)
        with self.assertRaisesRegex(RuntimeError, 'otro tópico'):
            self.execute('deploy')
        self.assertEqual(len(self.mutations), count)

    def test_additional_subscription_blocks_destroy(self):
        self.execute('deploy')
        self.subs['extra'] = {'name': 'extra', 'topic': next(iter(self.topics))}
        count = len(self.mutations)
        with self.assertRaisesRegex(RuntimeError, 'adicional'):
            self.execute('destroy', execute_destroy=True)
        self.assertEqual(len(self.mutations), count)

    def test_unowned_topic_not_adopted(self):
        self.execute('deploy')
        next(iter(self.topics.values()))['labels'].pop('component_id')
        with self.assertRaisesRegex(RuntimeError, 'pertenencia'):
            self.execute('deploy')

    def test_drift_detected_and_repaired(self):
        self.execute('deploy')
        sub = next(iter(self.subs.values()))
        sub['ackDeadlineSeconds'] = 20
        sub['retryPolicy'] = {'minimumBackoff': '10s'}
        count = len(self.mutations)
        with self.assertRaisesRegex(RuntimeError, 'configuración distinta'):
            self.execute('validate')
        self.assertEqual(len(self.mutations), count)
        self.assertEqual(self.execute('deploy'), 1)
        self.assertEqual(self.execute('validate'), 0)

    def test_advanced_feature_rejected(self):
        self.execute('deploy')
        next(iter(self.subs.values()))['enableExactlyOnceDelivery'] = True
        with self.assertRaisesRegex(RuntimeError, 'fuera de alcance'):
            self.execute('deploy')

    def test_invalid_retry_stops_before_cloud(self):
        self.config['SUBSCRIPTION_RETRY_POLICY'] = 'exponential'
        with self.assertRaises(ValueError):
            self.execute('deploy')
        self.assertFalse(self.calls)

    def test_default_message_storage_policy_is_not_modified(self):
        self.execute('deploy')
        for topic in self.topics.values():
            topic['messageStoragePolicy'] = {'allowedPersistenceRegions': ['us-central1']}
        self.assertEqual(self.execute('deploy'), 0)
        self.assertEqual(self.execute('validate'), 0)

    def test_cross_project_subscription_blocks_destroy(self):
        self.execute('deploy')
        original = self.fake
        def cross_project(config, *args):
            if args[:3] == ('pubsub', 'topics', 'list-subscriptions'):
                return ['https://pubsub.googleapis.com/v1/projects/other/subscriptions/external']
            return original(config, *args)
        count = len(self.mutations)
        with patch('infra.pubsub.manage.run', side_effect=cross_project):
            with self.assertRaisesRegex(RuntimeError, 'adicional vinculada'):
                manage(self.config, self.resources, self.manifest, 'destroy', execute_destroy=True)
        self.assertEqual(len(self.mutations), count)

    def test_missing_role_permission_stops_before_binding(self):
        original = self.fake
        def incomplete_role(config, *args):
            if args[:3] == ('iam', 'roles', 'describe'):
                return {'includedPermissions': []}
            return original(config, *args)
        with patch('infra.pubsub.manage.run', side_effect=incomplete_role):
            with self.assertRaisesRegex(RuntimeError, 'Rol no cubre'):
                manage(self.config, self.resources, self.manifest, 'deploy')
        self.assertFalse(self.mutations)

    def test_layer_label_rejected_for_pubsub(self):
        self.execute('deploy')
        next(iter(self.topics.values()))['labels']['layer'] = 'ingest'
        with self.assertRaisesRegex(RuntimeError, 'Layer no aplica'):
            self.execute('validate')

    def test_runtime_never_receives_binding(self):
        self.execute('deploy')
        assignments = [call for call in self.calls if call[:2] == ('projects', 'add-iam-policy-binding')]
        self.assertEqual(len(assignments), 1)
        self.assertNotIn(self.config['DATAFLOW_SERVICE_ACCOUNT_ID'], repr(assignments))

    def test_temporary_binding_cleaned_on_success_and_failure(self):
        with patch('infra.pubsub.manage.run', side_effect=self.fake):
            stats = manage(self.config, self.resources, self.manifest, 'deploy')
        self.assertEqual(stats['changes'], 3)
        self.assertEqual(stats['iam_changes'], 2)
        self.assertTrue(stats['temporary_binding_removed'])
        self.assertFalse(self.policy)
        next(iter(self.topics.values()))['labels'].pop('component_id')
        with self.assertRaises(RuntimeError):
            self.execute('validate')
        self.assertFalse(self.policy)

    def test_preexisting_binding_preserved(self):
        self.fake(self.config, 'projects', 'add-iam-policy-binding')
        original = copy.deepcopy(self.policy)
        with patch('infra.pubsub.manage.run', side_effect=self.fake):
            stats = manage(self.config, self.resources, self.manifest, 'deploy')
        self.assertEqual(stats['iam_changes'], 0)
        self.assertTrue(stats['preexisting_binding'])
        self.assertEqual(self.policy, original)

    def test_cleanup_error_reports_original_failure(self):
        original = self.fake
        def failure(config, *args):
            if args[:2] == ('projects', 'remove-iam-policy-binding'):
                raise RuntimeError('cleanup denied')
            if args[:3] == ('pubsub', 'topics', 'list'):
                raise RuntimeError('inventory denied')
            return original(config, *args)
        self.manifest['propagation_attempts'] = 1
        with patch('infra.pubsub.manage.run', side_effect=failure):
            with self.assertRaisesRegex(RuntimeError, 'cleanup denied.*inventory denied'):
                manage(self.config, self.resources, self.manifest, 'deploy')
