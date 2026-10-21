"""Storage 2.4: tres buckets, configuración declarativa e IAM temporal."""
import argparse
from contextlib import contextmanager
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


class StorageAPI:
    """JSON API oficial; creación atómica con labels. Token solo en memoria."""
    def __init__(self, config, manifest, impersonation):
        self.timeout = manifest['request_timeout_seconds']
        command = ['gcloud', 'auth', 'print-access-token',
                   '--account=' + config['BOOTSTRAP_ACCOUNT'],
                   '--project=' + config['GCP_PROJECT_ID'], impersonation, '--quiet']
        session = os.environ.copy()
        session.update(CLOUDSDK_CORE_PROJECT=config['GCP_PROJECT_ID'],
                       CLOUDSDK_COMPUTE_REGION=config['GCP_REGION'])
        result = subprocess.run(command, capture_output=True, text=True, timeout=self.timeout, env=session)
        if result.stderr:
            print(result.stderr, file=sys.stderr, end='')
        if result.returncode or not result.stdout.strip():
            raise RuntimeError('No se pudo obtener token del deployer; no se amplían permisos')
        self._token = result.stdout.strip()

    def request(self, method, path, body=None, query=None):
        url = 'https://storage.googleapis.com/storage/v1/' + path
        if query:
            url += '?' + urlencode(query)
        data = None if body is None else json.dumps(body).encode()
        request = Request(url, data=data, method=method, headers={
            'Authorization': 'Bearer ' + self._token, 'Content-Type': 'application/json'})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = response.read()
                return json.loads(payload) if payload else {}
        except HTTPError as error:
            # No exponer cabeceras, tokens ni cuerpos de datos en errores.
            try:
                message = json.loads(error.read()).get('error', {}).get('message', '')
            except (ValueError, OSError):
                message = error.reason
            raise RuntimeError(f'Cloud Storage HTTP {error.code}: {method} {path}: {message}') from None
        except URLError as error:
            raise RuntimeError('Conexión Cloud Storage falló: ' + str(error.reason)) from None

    def items(self, path, query):
        query = dict(query)
        while True:
            page = self.request('GET', path, query=query)
            yield from page.get('items', [])
            if not page.get('nextPageToken'):
                break
            query['pageToken'] = page['nextPageToken']


def check_config(config, manifest, resources):
    if set(manifest['buckets']) != {'RS-DATA-001', 'RS-DATA-002', 'RS-STR-004'}:
        raise ValueError('Inventario Storage fuera del corte aprobado')
    for key, expected in manifest['approved'].items():
        if config.get(key) != expected:
            raise ValueError(key + ' no coincide con el diseño aprobado')
    names = [resources[cid]['name'] for cid in manifest['buckets']]
    if len(set(names)) != len(names):
        raise ValueError('Bronze, Silver y técnico deben ser buckets distintos')
    if any(resources[cid]['scope'] != 'regional' for cid in manifest['buckets']):
        raise ValueError('Este corte requiere buckets regionales')


def desired(config, resource, spec):
    body = {
        'name': resource['name'], 'location': config['GCP_LOCATION'],
        'storageClass': config['STORAGE_CLASS'], 'labels': resource['labels'],
        'iamConfiguration': {
            'uniformBucketLevelAccess': {'enabled': config['STORAGE_UNIFORM_ACCESS'] == 'true'},
            'publicAccessPrevention': config['STORAGE_PUBLIC_ACCESS_PREVENTION']},
        'versioning': {'enabled': config['STORAGE_VERSIONING'] == 'true'},
        'softDeletePolicy': {'retentionDurationSeconds': config[spec['soft_delete_key']]},
        'lifecycle': {'rule': []},
    }
    if spec.get('lifecycle_age_key'):
        body['lifecycle']['rule'] = [{'action': {'type': 'Delete'},
                                      'condition': {'age': int(config[spec['lifecycle_age_key']])}}]
    return body


def current_properties(bucket):
    return {
        'storageClass': bucket.get('storageClass'),
        'labels': bucket.get('labels', {}),
        'iamConfiguration': {
            'uniformBucketLevelAccess': {'enabled': bucket.get('iamConfiguration', {}).get(
                'uniformBucketLevelAccess', {}).get('enabled', False)},
            'publicAccessPrevention': bucket.get('iamConfiguration', {}).get('publicAccessPrevention')},
        'versioning': {'enabled': bucket.get('versioning', {}).get('enabled', False)},
        'softDeletePolicy': {'retentionDurationSeconds': str(bucket.get('softDeletePolicy', {}).get(
            'retentionDurationSeconds', '0'))},
        'lifecycle': {'rule': bucket.get('lifecycle', {}).get('rule', [])},
    }


def check_existing(bucket, resource, config, project_number):
    if bucket.get('name') != resource['name'] or str(bucket.get('projectNumber')) != str(project_number):
        raise RuntimeError('Bucket de otro proyecto o nombre: ' + resource['name'])
    for key in ('component_id', 'managed_by'):
        if bucket.get('labels', {}).get(key) != resource['labels'][key]:
            raise RuntimeError('Conflicto de pertenencia: ' + resource['name'])
    if bucket.get('location', '').lower() != config['GCP_LOCATION'].lower():
        raise RuntimeError('Location incompatible; no se reemplaza ' + resource['name'])
    if bucket.get('locationType') not in (None, 'region'):
        raise RuntimeError('Scope no regional: ' + resource['name'])
    for field in ('retentionPolicy', 'encryption', 'autoclass', 'hierarchicalNamespace',
                  'customPlacementConfig', 'logging', 'ipFilter', 'defaultEventBasedHold'):
        value = bucket.get(field)
        if field in ('autoclass', 'hierarchicalNamespace'):
            value = (value or {}).get('enabled')
        if value:
            raise RuntimeError('Configuración fuera de alcance ' + field + ': ' + resource['name'])
    if bucket.get('versioning', {}).get('enabled'):
        raise RuntimeError('Versioning existente: revisar antes de modificar ' + resource['name'])
    # No publicar atributos de otra capa ni trasladar clasificaciones entre buckets.
    for key in ('layer', 'role', 'vertical'):
        if key not in resource['labels'] and key in bucket.get('labels', {}):
            raise RuntimeError('Label no aplicable ' + key + ': ' + resource['name'])


def needs_update(bucket, body):
    actual = current_properties(bucket)
    expected = {key: value for key, value in body.items() if key not in ('name', 'location')}
    # Conservar labels ajenos sin quitar trazabilidad requerida.
    actual_labels = actual.pop('labels')
    labels = expected.pop('labels')
    return actual != expected or any(actual_labels.get(key) != value for key, value in labels.items())


@contextmanager
def temporary_role(config, manifest, stats):
    email = config['DEPLOYER_SERVICE_ACCOUNT_ID'] + '@' + config['GCP_PROJECT_ID'] + '.iam.gserviceaccount.com'
    member = 'serviceAccount:' + email
    policy = run(config, 'projects', 'get-iam-policy', config['GCP_PROJECT_ID'])
    present = has_binding(policy, manifest['deployer_role'], member)
    created = not present
    stats['preexisting_binding'] = present
    failure = None
    try:
        if created:
            # Registrar intención antes de invocar; si el comando falla tras aplicar,
            # finally consulta y retira solo el binding ausente en el estado inicial.
            run(config, 'projects', 'add-iam-policy-binding', config['GCP_PROJECT_ID'],
                '--member=' + member, '--role=' + manifest['deployer_role'], '--condition=None')
            stats['iam_changes'] += 1
            print('[OK] Binding Storage temporal asignado por bootstrap', flush=True)
        else:
            print('[INFO] Binding preexistente: se conservará sin cambios', flush=True)
        yield '--impersonate-service-account=' + email
    except BaseException as error:
        failure = error
        raise
    finally:
        if created:
            try:
                policy = run(config, 'projects', 'get-iam-policy', config['GCP_PROJECT_ID'])
                if has_binding(policy, manifest['deployer_role'], member):
                    run(config, 'projects', 'remove-iam-policy-binding', config['GCP_PROJECT_ID'],
                        '--member=' + member, '--role=' + manifest['deployer_role'], '--condition=None')
                    stats['iam_changes'] += 1
                policy = run(config, 'projects', 'get-iam-policy', config['GCP_PROJECT_ID'])
                if has_binding(policy, manifest['deployer_role'], member):
                    raise RuntimeError('Binding temporal aún presente')
                stats['temporary_binding_removed'] = True
                print('[OK] Binding temporal retirado y política confirmada', flush=True)
            except Exception as cleanup_error:
                message = 'ERROR DE LIMPIEZA IAM: ' + str(cleanup_error)
                if failure:
                    message += '; operación original: ' + str(failure)
                raise RuntimeError(message) from cleanup_error


def inventory(api, config, manifest, newly_granted=False):
    attempts = manifest['propagation_attempts'] if newly_granted else 1
    for attempt in range(attempts):
        try:
            return {item['name']: item for item in api.items('b', {'project': config['GCP_PROJECT_ID']})}
        except RuntimeError as error:
            if 'HTTP 403:' not in str(error) or attempt + 1 == attempts:
                raise
            print(f'[WARN] Storage 403 tras grant; reintento {attempt + 1}/{attempts - 1}', flush=True)
            time.sleep(manifest['propagation_delay_seconds'])


def bucket_policy(api, name, runtime_email):
    policy = api.request('GET', 'b/' + quote(name, safe='') + '/iam')
    for binding in policy.get('bindings', []):
        members = set(binding.get('members', []))
        if members & {'allUsers', 'allAuthenticatedUsers'}:
            raise RuntimeError('Binding público detectado: ' + name)
        if 'serviceAccount:' + runtime_email in members:
            raise RuntimeError('Runtime Storage no aprobado todavía: ' + name)


def reconcile(api, config, resources, manifest, mode, stats, project_number,
              execute_destroy=False, purge=False, newly_granted=False):
    buckets = inventory(api, config, manifest, newly_granted)
    runtime = config['DATAFLOW_SERVICE_ACCOUNT_ID'] + '@' + config['GCP_PROJECT_ID'] + '.iam.gserviceaccount.com'
    for cid in manifest['buckets']:
        resource = resources[cid]
        if resource['name'] in buckets:
            check_existing(buckets[resource['name']], resource, config, project_number)
            bucket_policy(api, resource['name'], runtime)
    if mode == 'destroy':
        targets = [resources[cid]['name'] for cid in manifest['buckets'] if resources[cid]['name'] in buckets]
        print(json.dumps({'delete': targets, 'execute': execute_destroy, 'purge': purge}), flush=True)
        if not execute_destroy:
            return
        # Revisar TODOS los buckets antes de la primera eliminación.
        for name in targets:
            if next(api.items('b/' + quote(name, safe='') + '/o', {'versions': 'true', 'maxResults': 1}), None) and not purge:
                raise RuntimeError('Bucket con datos; requiere --purge: ' + name)
        for name in targets:
            path = 'b/' + quote(name, safe='')
            if purge:
                # Snapshot de identidades/generaciones para no saltar páginas al borrar.
                objects = list(api.items(path + '/o', {'versions': 'true'}))
                for obj in objects:
                    api.request('DELETE', path + '/o/' + quote(obj['name'], safe=''),
                                query={'generation': obj['generation'], 'ifGenerationMatch': obj['generation']})
            api.request('DELETE', path)
            stats['changes'] += 1
        remaining = inventory(api, config, manifest)
        if any(name in remaining for name in targets):
            raise RuntimeError('Destroy incompleto')
        print('[INFO] Bronze conserva recuperación soft delete; los datos eliminados pueden seguir facturándose 7 días', flush=True)
        return
    planned = []
    for cid, spec in manifest['buckets'].items():
        resource = resources[cid]
        body = desired(config, resource, spec)
        actual = buckets.get(resource['name'])
        if actual is None or needs_update(actual, body):
            planned.append((cid, actual, body))
    if mode == 'validate' and planned:
        raise RuntimeError('Buckets ausentes o con drift: ' + ', '.join(cid for cid, _, _ in planned))
    for cid, actual, body in planned:
        if actual is None:
            # API insert permite labels y protecciones en una única creación atómica.
            api.request('POST', 'b', body, {'project': config['GCP_PROJECT_ID']})
        else:
            patch = {k: v for k, v in body.items() if k not in ('name', 'location')}
            patch['labels'] = dict(actual.get('labels', {}), **body['labels'])
            api.request('PATCH', 'b/' + quote(body['name'], safe=''), patch,
                        {'ifMetagenerationMatch': actual['metageneration']})
        stats['changes'] += 1
        print('[OK] Aprovisionado ' + cid, flush=True)
    if planned:
        buckets = inventory(api, config, manifest)
    for cid, spec in manifest['buckets'].items():
        resource = resources[cid]
        actual = buckets.get(resource['name'])
        if not actual:
            raise RuntimeError('Bucket ausente tras deploy: ' + cid)
        check_existing(actual, resource, config, project_number)
        bucket_policy(api, resource['name'], runtime)
        if needs_update(actual, desired(config, resource, spec)):
            raise RuntimeError('Propiedades no confirmadas: ' + cid)
        print('[OK] ' + cid + ' ' + json.dumps(current_properties(actual), sort_keys=True), flush=True)


def manage(config, resources, manifest, mode, execute_destroy=False, purge=False):
    check_config(config, manifest, resources)
    stats = {'changes': 0, 'iam_changes': 0, 'temporary_binding_removed': False, 'mode': mode}
    enabled = run(config, 'services', 'list', '--enabled')
    if manifest['api'] not in {item['config']['name'] for item in enabled}:
        raise RuntimeError('API Storage no habilitada; no se habilita automáticamente')
    role = run(config, 'iam', 'roles', 'describe', manifest['deployer_role'])
    missing = set(manifest['required_permissions']) - set(role.get('includedPermissions', []))
    if missing:
        raise RuntimeError('Rol no cubre: ' + ', '.join(sorted(missing)))
    project = run(config, 'projects', 'describe', config['GCP_PROJECT_ID'])
    if project.get('projectId') != config['GCP_PROJECT_ID'] or project.get('lifecycleState') != 'ACTIVE':
        raise RuntimeError('Proyecto no coincide o no está ACTIVE')
    if not project.get('projectNumber'):
        raise RuntimeError('Proyecto sin número verificable')
    policy = run(config, 'projects', 'get-iam-policy', config['GCP_PROJECT_ID'])
    runtime = 'serviceAccount:' + config['DATAFLOW_SERVICE_ACCOUNT_ID'] + '@' + config['GCP_PROJECT_ID'] + '.iam.gserviceaccount.com'
    for binding in policy.get('bindings', []):
        if runtime in binding.get('members', []) and binding['role'].startswith('roles/storage.'):
            raise RuntimeError('Runtime ya tiene permisos Storage directos; revisión requerida')
    with temporary_role(config, manifest, stats) as impersonation:
        api = StorageAPI(config, manifest, impersonation)
        reconcile(api, config, resources, manifest, mode, stats, project['projectNumber'],
                  execute_destroy, purge, newly_granted=stats['iam_changes'] > 0)
    print(json.dumps(stats), flush=True)
    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'config/dev.env')
    parser.add_argument('--manifest', type=Path, default=ROOT / 'infra/config/storage.json')
    parser.add_argument('--mode', choices=('deploy', 'validate', 'destroy'), default='validate')
    parser.add_argument('--execute-destroy', action='store_true')
    parser.add_argument('--purge', action='store_true', help='Eliminar también objetos; Bronze mantiene soft delete')
    args = parser.parse_args()
    try:
        if (args.execute_destroy or args.purge) and args.mode != 'destroy':
            raise ValueError('Opciones destructivas requieren --mode destroy')
        if args.purge and not args.execute_destroy:
            raise ValueError('--purge requiere --execute-destroy')
        config, resources = load(args.config)
        manifest = json.loads(args.manifest.read_text())
        manage(config, resources, manifest, args.mode, args.execute_destroy, args.purge)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
