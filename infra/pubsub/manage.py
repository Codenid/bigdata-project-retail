"""Pub/Sub 2.3: dos tópicos y una subscription pull del catálogo."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from infra.bootstrap.apis import run
from infra.config.settings import ROOT, load
from infra.iam.manage import has_binding


def validate_config(config, manifest):
    if (manifest['topics'] != ['RS-STR-001', 'RS-STR-003'] or
            manifest['subscription'] != 'RS-STR-002' or manifest['source_topic'] != 'RS-STR-001'):
        raise ValueError('Inventario Pub/Sub distinto al corte aprobado')
    if config['SUBSCRIPTION_EXPIRATION'] == 'never':
        raise ValueError('Esta fase requiere expiración finita en segundos')
    for key, expected in (('RETAIN_ACKED_MESSAGES', 'false'), ('SUBSCRIPTION_RETRY_POLICY', 'immediate')):
        if config.get(key) != expected:
            raise ValueError(f'{key} debe ser {expected}')


def full_name(config, kind, resource):
    return f"projects/{config['GCP_PROJECT_ID']}/{kind}/{resource['name']}"


def ownership(actual, resource):
    if 'layer' in actual.get('labels', {}) and 'layer' not in resource['labels']:
        raise RuntimeError('Layer no aplica a este recurso: ' + actual['name'])
    if actual.get('labels', {}).get('component_id') != resource['labels']['component_id'] or actual.get('labels', {}).get('managed_by') != resource['labels']['managed_by']:
        raise RuntimeError('Conflicto de pertenencia: ' + actual['name'])


def labels_match(actual, resource):
    return all(actual.get('labels', {}).get(key) == value for key, value in resource['labels'].items())


def check_features(actual, fields):
    for field in fields:
        if actual.get(field):
            raise RuntimeError(f"Feature fuera de alcance {field}: {actual['name']}")


def subscription_matches(actual, config):
    return (actual.get('ackDeadlineSeconds') == int(config['ACK_DEADLINE_SECONDS']) and
            actual.get('messageRetentionDuration') == config['MESSAGE_RETENTION_SECONDS'] + 's' and
            not actual.get('retainAckedMessages', False) and
            actual.get('expirationPolicy', {}).get('ttl') == config['SUBSCRIPTION_EXPIRATION'] + 's' and
            not actual.get('retryPolicy'))


def inventory(config, impersonation):
    flags = (impersonation,) if impersonation else ()
    topics = {r['name']: r for r in run(config, 'pubsub', 'topics', 'list', *flags)}
    subs = {r['name']: r for r in run(config, 'pubsub', 'subscriptions', 'list', *flags)}
    return topics, subs


def preflight_resources(config, resources, manifest, topics, subs):
    expected_sub = full_name(config, 'subscriptions', resources[manifest['subscription']])
    source = full_name(config, 'topics', resources[manifest['source_topic']])
    for cid in manifest['topics']:
        name = full_name(config, 'topics', resources[cid])
        if name in topics:
            ownership(topics[name], resources[cid])
            check_features(topics[name], manifest['topic_disabled_fields'])
        for sub in subs.values():
            if sub.get('topic') == name and (sub['name'] != expected_sub or name != source):
                raise RuntimeError('Subscription adicional encontrada: ' + sub['name'])
    if expected_sub in subs:
        sub = subs[expected_sub]
        ownership(sub, resources[manifest['subscription']])
        if sub.get('topic') != source:
            raise RuntimeError('La subscription apunta a otro tópico; no se reemplaza')
        check_features(sub, manifest['subscription_disabled_fields'])


def manage(config, resources, manifest, mode, execute_destroy=False, remove_binding=False):
    validate_config(config, manifest)
    # No se habilitan APIs: la fase 2.1 debe estar completa.
    enabled = run(config, 'services', 'list', '--enabled')
    if manifest['api'] not in {s['config']['name'] for s in enabled}:
        raise RuntimeError('API Pub/Sub no habilitada; no se habilita automáticamente')
    role = run(config, 'iam', 'roles', 'describe', manifest['deployer_role'])
    missing = set(manifest['required_permissions']) - set(role.get('includedPermissions', []))
    if missing:
        raise RuntimeError('Rol no cubre permisos: ' + ', '.join(sorted(missing)))
    deployer = config['DEPLOYER_SERVICE_ACCOUNT_ID'] + '@' + config['GCP_PROJECT_ID'] + '.iam.gserviceaccount.com'
    runtime = config['DATAFLOW_SERVICE_ACCOUNT_ID'] + '@' + config['GCP_PROJECT_ID'] + '.iam.gserviceaccount.com'
    member = 'serviceAccount:' + deployer
    policy = run(config, 'projects', 'get-iam-policy', config['GCP_PROJECT_ID'])
    for binding in policy.get('bindings', []):
        if binding['role'].startswith('roles/pubsub.') and 'serviceAccount:' + runtime in binding.get('members', []):
            raise RuntimeError('Runtime ya tiene un rol Pub/Sub directo; revisar antes de continuar')
    binding_exists = has_binding(policy, manifest['deployer_role'], member)
    changes = 0
    if not binding_exists and mode != 'destroy':
        if mode != 'deploy':
            raise RuntimeError('Falta binding Pub/Sub del deployer; ejecutar deploy')
        run(config, 'projects', 'add-iam-policy-binding', config['GCP_PROJECT_ID'],
            '--member=' + member, '--role=' + manifest['deployer_role'], '--condition=None')
        changes += 1
        print('[OK] Binding temporal de aprovisionamiento aplicado', flush=True)
    impersonation = '--impersonate-service-account=' + deployer if binding_exists or mode == 'deploy' else None
    topics, subs = inventory(config, impersonation)
    preflight_resources(config, resources, manifest, topics, subs)
    sub_cid = manifest['subscription']
    if mode == 'destroy':
        planned = [full_name(config, 'subscriptions', resources[sub_cid])]
        planned += [full_name(config, 'topics', resources[cid]) for cid in manifest['topics']]
        # Consultar conexiones desde cada tópico también detecta subscriptions de otros proyectos.
        for cid in manifest['topics']:
            topic_name = full_name(config, 'topics', resources[cid])
            if topic_name not in topics:
                continue
            flags = (impersonation,) if impersonation else ()
            attached = run(config, 'pubsub', 'topics', 'list-subscriptions', topic_name, '--uri', *flags)
            allowed = {planned[0]} if cid == manifest['source_topic'] else set()
            for uri in attached:
                attached_name = 'projects/' + uri.split('/projects/', 1)[1] if '/projects/' in uri else uri
                if attached_name not in allowed:
                    raise RuntimeError('Subscription adicional vinculada al tópico: ' + attached_name)
        print(json.dumps({'delete': [name for name in planned if name in subs or name in topics],
                          'execute': execute_destroy, 'remove_deployer_binding': remove_binding}), flush=True)
        if not execute_destroy:
            return 0
        if not impersonation and any(name in topics or name in subs for name in planned):
            raise RuntimeError('Falta binding del deployer para destruir; ejecutar deploy primero')
        # --execute-destroy reconoce que se pierde el backlog de estos recursos.
        for kind, cid in [('subscriptions', sub_cid)] + [('topics', cid) for cid in manifest['topics']]:
            name = full_name(config, kind, resources[cid])
            if name in (subs if kind == 'subscriptions' else topics):
                run(config, 'pubsub', kind, 'delete', name, impersonation)
                changes += 1
        topics, subs = inventory(config, impersonation)
        if any(name in topics or name in subs for name in planned):
            raise RuntimeError('Destroy incompleto')
        if remove_binding and binding_exists:
            run(config, 'projects', 'remove-iam-policy-binding', config['GCP_PROJECT_ID'],
                '--member=' + member, '--role=' + manifest['deployer_role'], '--condition=None')
            changes += 1
        print(json.dumps({'changes': changes, 'mode': mode}), flush=True)
        return changes
    # Plan completo: no mutar recursos hasta validar todos los existentes.
    operations = []
    for cid in manifest['topics']:
        resource = resources[cid]
        name = full_name(config, 'topics', resource)
        labels = ','.join(f'{k}={v}' for k, v in sorted(resource['labels'].items()))
        if name not in topics:
            operations.append(('topics', 'create', name, '--labels=' + labels))
        elif not labels_match(topics[name], resource):
            operations.append(('topics', 'update', name, '--update-labels=' + labels))
    resource = resources[sub_cid]
    name = full_name(config, 'subscriptions', resource)
    exists = name in subs
    if not exists or not (labels_match(subs[name], resource) and subscription_matches(subs[name], config)):
        labels = ','.join(f'{k}={v}' for k, v in sorted(resource['labels'].items()))
        flags = [('--update-labels=' if exists else '--labels=') + labels,
                 '--ack-deadline=' + config['ACK_DEADLINE_SECONDS'],
                 '--message-retention-duration=' + config['MESSAGE_RETENTION_SECONDS'] + 's',
                 '--expiration-period=' + config['SUBSCRIPTION_EXPIRATION'] + 's',
                 '--no-retain-acked-messages']
        if exists:
            flags.append('--clear-retry-policy')
        else:
            flags.append('--topic=' + full_name(config, 'topics', resources[manifest['source_topic']]))
        operations.append(('subscriptions', 'update' if exists else 'create', name, *flags))
    if mode == 'validate' and operations:
        raise RuntimeError('Recursos ausentes o configuración distinta: ' + repr(operations))
    for operation in operations:
        run(config, 'pubsub', *operation, impersonation)
        changes += 1
    if operations:
        topics, subs = inventory(config, impersonation)
    preflight_resources(config, resources, manifest, topics, subs)
    for cid in manifest['topics']:
        actual = topics.get(full_name(config, 'topics', resources[cid]))
        if not actual or not labels_match(actual, resources[cid]):
            raise RuntimeError('Validación falló para ' + cid)
        print('[OK] ' + cid, flush=True)
    actual = subs.get(name)
    if not actual or not labels_match(actual, resource) or not subscription_matches(actual, config):
        raise RuntimeError('Validación falló para ' + sub_cid)
    print('[OK] ' + sub_cid + ' pull y propiedades aprobadas', flush=True)
    print('[INFO] Message Storage Policy observada, no configurada por el script', flush=True)
    print(json.dumps({'changes': changes, 'mode': mode}), flush=True)
    return changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'config/dev.env')
    parser.add_argument('--manifest', type=Path, default=ROOT / 'infra/config/pubsub.json')
    parser.add_argument('--mode', choices=('deploy', 'validate', 'destroy'), default='validate')
    parser.add_argument('--execute-destroy', action='store_true', help='Eliminar recursos y sus mensajes pendientes')
    parser.add_argument('--remove-deployer-binding', action='store_true', help='Retirar también el binding temporal aprobado')
    args = parser.parse_args()
    try:
        if (args.execute_destroy or args.remove_deployer_binding) and args.mode != 'destroy':
            raise ValueError('Opciones destructivas requieren --mode destroy')
        config, resources = load(args.config)
        manifest = json.loads(args.manifest.read_text())
        manage(config, resources, manifest, args.mode, args.execute_destroy, args.remove_deployer_binding)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
