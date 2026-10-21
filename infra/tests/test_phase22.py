import copy
import json
import unittest
from unittest.mock import patch

from infra.config.settings import ROOT
from infra.iam.manage import manage, has_binding
from infra.bootstrap.apis import run


class Phase22(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / 'infra/config/iam.json').read_text())
        self.config = {'GCP_PROJECT_ID': 'academic-test', 'BOOTSTRAP_ACCOUNT': 'test@example.com',
                       'DATAFLOW_SERVICE_ACCOUNT_ID': 'runtime', 'DEPLOYER_SERVICE_ACCOUNT_ID': 'deployer'}
        self.resources = {cid: {'labels': {'component_id': cid.lower()}}
                          for cid in self.manifest['accounts']}
        self.accounts = {}
        self.policies = {}
        self.mutations = []

    def fake(self, config, *args):
        if args[:3] == ('iam', 'roles', 'describe'):
            return {'includedPermissions': self.manifest['viewer_permissions']}
        if args[:2] == ('projects', 'get-iam-policy'):
            return {}
        action = args[2]
        if action == 'list':
            return list(self.accounts.values())
        email = args[3]
        if action in ('create', 'update'):
            if action == 'create':
                email += '@academic-test.iam.gserviceaccount.com'
            self.accounts[email] = {'email': email, 'displayName': args[4].split('=', 1)[1],
                                    'description': args[5].split('=', 1)[1]}
            self.mutations.append(action)
            return self.accounts[email]
        if action == 'get-iam-policy':
            return copy.deepcopy(self.policies.get(email, {}))
        if action == 'add-iam-policy-binding':
            member = args[4].split('=', 1)[1]
            role = args[5].split('=', 1)[1]
            self.policies.setdefault(email, {}).setdefault('bindings', []).append(
                {'role': role, 'members': [member]})
            self.mutations.append(action)
            return self.policies[email]
        if action == 'describe':
            return self.accounts[email]
        raise AssertionError(args)

    def test_create_validate_repeat(self):
        with patch('infra.iam.manage.run', side_effect=self.fake):
            self.assertEqual(manage(self.config, self.resources, self.manifest, 'deploy'), 5)
            self.assertEqual(manage(self.config, self.resources, self.manifest, 'validate'), 0)
            self.assertEqual(manage(self.config, self.resources, self.manifest, 'deploy'), 0)
        self.assertEqual(len(self.accounts), 2)
        self.assertEqual(len(self.mutations), 5)

    def test_missing_permission_blocks_all_changes(self):
        with patch('infra.iam.manage.run', return_value={'includedPermissions': []}):
            with self.assertRaisesRegex(RuntimeError, 'Viewer no cubre'):
                manage(self.config, self.resources, self.manifest, 'deploy')
        self.assertFalse(self.mutations)

    def test_permission_denied_not_treated_as_absent(self):
        with patch('infra.iam.manage.run', side_effect=RuntimeError('PERMISSION_DENIED')):
            with self.assertRaises(RuntimeError):
                manage(self.config, self.resources, self.manifest, 'deploy')
        self.assertFalse(self.mutations)

    def test_forbidden_project_role_stops_mutations(self):
        original = self.fake
        def forbidden(config, *args):
            if args[:2] == ('projects', 'get-iam-policy'):
                return {'bindings': [{'role': 'roles/editor', 'members': [
                    'serviceAccount:runtime@academic-test.iam.gserviceaccount.com']}]}
            return original(config, *args)
        with patch('infra.iam.manage.run', side_effect=forbidden):
            with self.assertRaisesRegex(RuntimeError, 'Binding amplio'):
                manage(self.config, self.resources, self.manifest, 'deploy')
        self.assertFalse(self.mutations)

    def test_predefined_role_query_has_no_project_flag(self):
        config = dict(self.config, GCP_REGION='us-central1')
        with patch('infra.bootstrap.apis.subprocess.run') as process:
            process.return_value.returncode = 0
            process.return_value.stderr = ''
            process.return_value.stdout = '{}'
            run(config, 'iam', 'roles', 'describe', self.manifest['viewer_role'])
            self.assertNotIn('--project', process.call_args.args[0])

    def test_validate_absent_never_creates(self):
        with patch('infra.iam.manage.run', side_effect=self.fake):
            with self.assertRaisesRegex(RuntimeError, 'Falta identidad'):
                manage(self.config, self.resources, self.manifest, 'validate')
        self.assertFalse(self.mutations)

    def test_conditional_binding_does_not_count_as_unconditional(self):
        self.assertFalse(has_binding({'bindings': [{'role': 'viewer', 'members': ['x'],
                                                   'condition': {'expression': 'false'}}]}, 'viewer', 'x'))

    def test_forbidden_manifest_role_rejected_before_cloud(self):
        self.manifest['viewer_role'] = self.manifest['forbidden_roles'][0]
        with patch('infra.iam.manage.run') as cloud:
            with self.assertRaisesRegex(ValueError, 'Rol prohibido'):
                manage(self.config, self.resources, self.manifest, 'deploy')
        cloud.assert_not_called()
