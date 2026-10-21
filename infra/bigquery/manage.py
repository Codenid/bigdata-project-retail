"""FASE 2.5: dataset Gold vacío, sin jobs y con accesos temporales controlados."""
import argparse
from collections import Counter
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from infra.bootstrap.apis import run
from infra.config.settings import ROOT, load
from infra.iam.manage import has_binding


class APIError(RuntimeError):
    def __init__(self, status, message):
        self.status = status
        super().__init__(f'BigQuery/API HTTP {status}: {message}')


class BigQueryAPI:
    """JSON API oficial; tokens bootstrap/deployer solo en memoria, sin SQL."""
    def __init__(self, config, manifest, impersonation=None):
        self.project = config['GCP_PROJECT_ID']
        self.timeout = manifest['request_timeout_seconds']
        command = ['gcloud', 'auth', 'print-access-token', '--account=' + config['BOOTSTRAP_ACCOUNT'],
                   '--project=' + self.project, '--quiet']
        if impersonation:
            command.append(impersonation)
        session = os.environ.copy()
        session.update(CLOUDSDK_CORE_PROJECT=self.project, CLOUDSDK_COMPUTE_REGION=config['GCP_REGION'],
                       CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT='')
        result = subprocess.run(command, text=True, capture_output=True, timeout=self.timeout, env=session)
        if result.stderr:
            print(result.stderr, file=sys.stderr, end='')
        if result.returncode or not result.stdout.strip():
            raise RuntimeError('No se pudo autenticar la identidad configurada')
        self._token = result.stdout.strip()

    def _request(self, method, url, body=None, etag=None):
        headers = {'Authorization': 'Bearer ' + self._token, 'Content-Type': 'application/json'}
        if etag:
            headers['If-Match'] = etag
        request = Request(url, method=method, headers=headers,
                          data=None if body is None else json.dumps(body).encode())
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = response.read()
                return json.loads(payload) if payload else {}
        except HTTPError as error:
            try:
                message = json.loads(error.read()).get('error', {}).get('message', '')
            except (ValueError, OSError):
                message = str(error.reason)
            raise APIError(error.code, message) from None
        except URLError as error:
            raise RuntimeError('Conexión API falló: ' + str(error.reason)) from None

    def request(self, method, path, body=None, query=None, etag=None):
        url = 'https://bigquery.googleapis.com/bigquery/v2/' + path
        if query:
            url += '?' + urlencode(query)
        return self._request(method, url, body, etag)

    def project_permissions(self, permissions):
        url = 'https://cloudresourcemanager.googleapis.com/v1/projects/' + quote(self.project, safe='') + ':testIamPermissions'
        return self._request('POST', url, {'permissions': permissions}).get('permissions', [])


def dataset_path(config):
    return 'projects/' + quote(config['GCP_PROJECT_ID'], safe='') + '/datasets/' + quote(config['GOLD_DATASET_ID'], safe='')


def get_dataset(api, path):
    try:
        return api.request('GET', path, query={'datasetView': 'FULL', 'accessPolicyVersion': 3})
    except APIError as error:
        if error.status == 404:
            return None
        raise


def principal_matches(entry, email):
    return entry.get('userByEmail') == email or entry.get('iamMember') in ('serviceAccount:' + email, 'user:' + email)


def owner(entry, email, manifest):
    return (principal_matches(entry, email) and not entry.get('condition') and
            entry.get('role') in (manifest['dataset_role'], manifest['dataset_owner_alias']))


def access_key(entry, manifest):
    entry = deepcopy(entry)
    if entry.get('role') == manifest['dataset_owner_alias']:
        entry['role'] = manifest['dataset_role']
    if entry.get('iamMember', '').startswith(('serviceAccount:', 'user:')):
        entry['userByEmail'] = entry.pop('iamMember').split(':', 1)[1]
    return json.dumps(entry, sort_keys=True)


def without_new_owner(access, baseline, email, manifest):
    counts = Counter(access_key(entry, manifest) for entry in baseline)
    result = []
    for entry in access:
        key = access_key(entry, manifest)
        if counts[key]:
            counts[key] -= 1
            result.append(entry)
        elif not owner(entry, email, manifest):
            result.append(entry)
    return result


def assert_bootstrap_admin(api, manifest):
    required = set(manifest['bootstrap_admin_permissions'])
    missing = required - set(api.project_permissions(sorted(required)))
    if missing:
        raise RuntimeError('Bootstrap sin administración efectiva heredada suficiente: ' + ', '.join(sorted(missing)))
    print('[OK] Bootstrap conserva permisos administrativos efectivos del proyecto', flush=True)


def check_dataset(dataset, config, resource):
    reference = dataset.get('datasetReference', {})
    if reference != {'projectId': config['GCP_PROJECT_ID'], 'datasetId': resource['name']}:
        raise RuntimeError('Dataset de otro proyecto o nombre')
    labels = dataset.get('labels', {})
    if any(labels.get(key) != resource['labels'][key] for key in ('component_id', 'managed_by')):
        raise RuntimeError('Dataset sin pertenencia verificable; no se adopta')
    if dataset.get('location', '').lower() != config['GCP_LOCATION'].lower():
        raise RuntimeError('Location incompatible; no se reemplaza el dataset')
    for field in ('defaultEncryptionConfiguration', 'externalDatasetReference', 'linkedDatasetSource',
                  'externalCatalogDatasetOptions', 'isCaseInsensitive'):
        if dataset.get(field):
            raise RuntimeError('Propiedad fuera de alcance: ' + field)
    runtime = config['DATAFLOW_SERVICE_ACCOUNT_ID'] + '@' + config['GCP_PROJECT_ID'] + '.iam.gserviceaccount.com'
    for entry in dataset.get('access', []):
        if principal_matches(entry, runtime):
            raise RuntimeError('Runtime BigQuery no aprobado todavía')
        if entry.get('specialGroup') in ('allAuthenticatedUsers', 'allUsers') or entry.get('iamMember') in ('allUsers', 'allAuthenticatedUsers'):
            raise RuntimeError('Acceso público detectado')


def assert_empty(api, path):
    for kind in ('tables', 'models', 'routines'):
        page = api.request('GET', path + '/' + kind, query={'maxResults': 1})
        if page.get(kind) or page.get('nextPageToken'):
            raise RuntimeError('Dataset contiene artefactos: ' + kind + '; no se modifica ni elimina')


def metadata_patch(dataset, resource, manifest):
    patch = {}
    labels = dict(dataset.get('labels', {}), **resource['labels'])
    if labels != dataset.get('labels', {}):
        patch['labels'] = labels
    for field, expected in manifest['dataset_defaults'].items():
        if dataset.get(field) != expected:
            patch[field] = expected
    for field, expected in (('friendlyName', manifest['friendly_name']), ('description', manifest['description'])):
        if dataset.get(field) != expected:
            patch[field] = expected
    # storageBillingModel deliberadamente no se envía ni modifica.
    return patch


def retry_read(api, path, manifest):
    for attempt in range(manifest['propagation_attempts']):
        try:
            dataset = get_dataset(api, path)
            if dataset is None:
                raise RuntimeError('Dataset desapareció durante la operación')
            return dataset
        except APIError as error:
            if error.status != 403 or attempt + 1 == manifest['propagation_attempts']:
                raise
            print(f'[WARN] BigQuery 403 tras grant; reintento {attempt + 1}', flush=True)
            time.sleep(manifest['propagation_delay_seconds'])


def manage(config, resources, manifest, mode, execute_destroy=False):
    if manifest['component_id'] != 'RS-DATA-003' or resources['RS-DATA-003']['scope'] != 'regional':
        raise ValueError('Solo RS-DATA-003 regional está aprobado')
    if manifest['dataset_defaults'] != {'defaultTableExpirationMs': None, 'defaultPartitionExpirationMs': None}:
        raise ValueError('Esta fase no configura expiraciones')
    resource = resources[manifest['component_id']]
    enabled = run(config, 'services', 'list', '--enabled')
    if manifest['api'] not in {item['config']['name'] for item in enabled}:
        raise RuntimeError('BigQuery API no habilitada; no se habilita automáticamente')
    for role, permissions in ((manifest['creation_role'], manifest['creation_permissions']),
                              (manifest['dataset_role'], manifest['dataset_permissions'])):
        definition = run(config, 'iam', 'roles', 'describe', role)
        if set(permissions) - set(definition.get('includedPermissions', [])):
            raise RuntimeError('Rol no cubre operaciones aprobadas: ' + role)
    project_policy = run(config, 'projects', 'get-iam-policy', config['GCP_PROJECT_ID'])
    email = config['DEPLOYER_SERVICE_ACCOUNT_ID'] + '@' + config['GCP_PROJECT_ID'] + '.iam.gserviceaccount.com'
    member = 'serviceAccount:' + email
    runtime = 'serviceAccount:' + config['DATAFLOW_SERVICE_ACCOUNT_ID'] + '@' + config['GCP_PROJECT_ID'] + '.iam.gserviceaccount.com'
    for binding in project_policy.get('bindings', []):
        if runtime in binding.get('members', []) and binding['role'].startswith('roles/bigquery.'):
            raise RuntimeError('Runtime con permisos BigQuery directos; revisión requerida')
    bootstrap = BigQueryAPI(config, manifest)
    assert_bootstrap_admin(bootstrap, manifest)
    path = dataset_path(config)
    initial = get_dataset(bootstrap, path)
    if initial is not None:
        check_dataset(initial, config, resource)
        assert_empty(bootstrap, path)
    if initial is None and mode != 'deploy':
        if mode == 'destroy':
            print(json.dumps({'changes': 0, 'mode': mode, 'dataset_absent': True}), flush=True)
            return {'changes': 0, 'mode': mode}
        raise RuntimeError('Dataset ausente; ejecutar deploy')
    baseline = deepcopy(initial.get('access', [])) if initial else []
    preexisting_owner = any(owner(entry, email, manifest) for entry in baseline)
    stats = {'changes': 0, 'project_iam_changes': 0, 'dataset_iam_changes': 0, 'mode': mode,
             'preexisting_dataset_owner': preexisting_owner, 'automatic_creator_owner_detected': False}
    project_added = False
    touch_owner = False
    failure = None
    try:
        if initial is None:
            if not has_binding(project_policy, manifest['creation_role'], member):
                project_added = True
                run(config, 'projects', 'add-iam-policy-binding', config['GCP_PROJECT_ID'],
                    '--member=' + member, '--role=' + manifest['creation_role'], '--condition=None')
                stats['project_iam_changes'] += 1
                print('[OK] BigQuery User temporal asignado para creación', flush=True)
            deployer = BigQueryAPI(config, manifest, '--impersonate-service-account=' + email)
            body = {'datasetReference': {'projectId': config['GCP_PROJECT_ID'], 'datasetId': resource['name']},
                    'location': config['GCP_LOCATION'], 'labels': resource['labels'],
                    'friendlyName': manifest['friendly_name'], 'description': manifest['description'],
                    'access': deepcopy(manifest['initial_access'])}
            # Desde la intención de insert, inspeccionar y limpiar un eventual grant
            # automático aun si el servidor creó el dataset y se perdió la respuesta.
            touch_owner = True
            for attempt in range(manifest['propagation_attempts']):
                try:
                    deployer.request('POST', 'projects/' + quote(config['GCP_PROJECT_ID'], safe='') + '/datasets', body)
                    break
                except APIError as error:
                    if error.status == 409:
                        touch_owner = False  # Nunca limpiar ACL de una creación concurrente/preexistente.
                    if error.status != 403 or attempt + 1 == manifest['propagation_attempts']:
                        raise
                    print(f'[WARN] Creación 403 tras grant; reintento {attempt + 1}', flush=True)
                    time.sleep(manifest['propagation_delay_seconds'])
            stats['changes'] += 1
            current = get_dataset(bootstrap, path)
            if current is None:
                raise RuntimeError('Dataset no confirmado tras creación')
            stats['automatic_creator_owner_detected'] = any(owner(entry, email, manifest) for entry in current.get('access', []))
            observed = [entry for entry in current.get('access', []) if not owner(entry, email, manifest)]
            if Counter(access_key(entry, manifest) for entry in observed) != Counter(
                    access_key(entry, manifest) for entry in manifest['initial_access']):
                raise RuntimeError('ACL inicial inesperada: revisar sin ampliar ni borrar accesos automáticamente')
        else:
            current = initial
            deployer = BigQueryAPI(config, manifest, '--impersonate-service-account=' + email)
        check_dataset(current, config, resource)
        assert_empty(bootstrap, path)
        if not any(owner(entry, email, manifest) for entry in current.get('access', [])):
            touch_owner = True
            access = deepcopy(current.get('access', []))
            access.append({'role': manifest['dataset_role'], 'userByEmail': email})
            bootstrap.request('PATCH', path, {'access': access}, etag=current['etag'])
            stats['dataset_iam_changes'] += 1
            print('[OK] Data Owner temporal limitado al dataset', flush=True)
        actual = retry_read(deployer, path, manifest)
        check_dataset(actual, config, resource)
        assert_empty(deployer, path)
        if mode == 'destroy':
            print(json.dumps({'delete': resource['name'], 'execute': execute_destroy, 'recursive': False}), flush=True)
            if execute_destroy:
                assert_bootstrap_admin(bootstrap, manifest)
                deployer.request('DELETE', path, query={'deleteContents': 'false'})
                stats['changes'] += 1
                if get_dataset(bootstrap, path) is not None:
                    raise RuntimeError('Dataset aún presente tras destroy')
        else:
            patch = metadata_patch(actual, resource, manifest)
            if patch:
                if mode != 'deploy':
                    raise RuntimeError('Dataset con drift: ' + ', '.join(patch))
                deployer.request('PATCH', path, patch, etag=actual['etag'])
                stats['changes'] += 1
                actual = get_dataset(deployer, path)
            if actual is None or metadata_patch(actual, resource, manifest):
                raise RuntimeError('Propiedades no confirmadas')
            assert_empty(deployer, path)
            print('[OK] RS-DATA-003 vacío; location, labels y expiraciones nulas verificados', flush=True)
            print(json.dumps({'location': actual['location'], 'labels': actual.get('labels'),
                              'defaultTableExpirationMs': actual.get('defaultTableExpirationMs'),
                              'defaultPartitionExpirationMs': actual.get('defaultPartitionExpirationMs'),
                              'storageBillingModel_observed': actual.get('storageBillingModel'),
                              'storageBillingModel_configured': False}), flush=True)
    except BaseException as error:
        failure = error
        raise
    finally:
        cleanup_errors = []
        if touch_owner:
            try:
                current = get_dataset(bootstrap, path)
                if current is not None:
                    check_dataset(current, config, resource)
                    cleaned = without_new_owner(current.get('access', []), baseline, email, manifest)
                    if cleaned != current.get('access', []):
                        # Probar bootstrap con permisos actuales antes de retirar al creador.
                        assert_bootstrap_admin(bootstrap, manifest)
                        bootstrap.request('PATCH', path, {'access': cleaned}, etag=current['etag'])
                        stats['dataset_iam_changes'] += 1
                    confirmed = get_dataset(bootstrap, path)
                    if confirmed is None or without_new_owner(confirmed.get('access', []), baseline, email, manifest) != confirmed.get('access', []):
                        raise RuntimeError('Acceso temporal/automático Data Owner aún presente')
                stats['temporary_dataset_access_removed'] = True
                print('[OK] Acceso temporal del dataset retirado; administración bootstrap conservada', flush=True)
            except Exception as error:
                cleanup_errors.append('ACL dataset: ' + str(error))
        if project_added:
            try:
                current_policy = run(config, 'projects', 'get-iam-policy', config['GCP_PROJECT_ID'])
                if has_binding(current_policy, manifest['creation_role'], member):
                    run(config, 'projects', 'remove-iam-policy-binding', config['GCP_PROJECT_ID'],
                        '--member=' + member, '--role=' + manifest['creation_role'], '--condition=None')
                    stats['project_iam_changes'] += 1
                confirmed = run(config, 'projects', 'get-iam-policy', config['GCP_PROJECT_ID'])
                if has_binding(confirmed, manifest['creation_role'], member):
                    raise RuntimeError('BigQuery User temporal aún presente')
                stats['temporary_project_access_removed'] = True
                print('[OK] BigQuery User temporal retirado y política confirmada', flush=True)
            except Exception as error:
                cleanup_errors.append('IAM proyecto: ' + str(error))
        if cleanup_errors:
            message = 'ERROR DE LIMPIEZA: ' + '; '.join(cleanup_errors)
            if failure:
                message += '; operación original: ' + str(failure)
            raise RuntimeError(message)
    print(json.dumps(stats), flush=True)
    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'config/dev.env')
    parser.add_argument('--manifest', type=Path, default=ROOT / 'infra/config/bigquery.json')
    parser.add_argument('--mode', choices=('deploy', 'validate', 'destroy'), default='validate')
    parser.add_argument('--execute-destroy', action='store_true')
    args = parser.parse_args()
    try:
        if args.execute_destroy and args.mode != 'destroy':
            raise ValueError('--execute-destroy requiere --mode destroy')
        config, resources = load(args.config)
        manifest = json.loads(args.manifest.read_text())
        manage(config, resources, manifest, args.mode, args.execute_destroy)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
