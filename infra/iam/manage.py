"""FASE 2.2: dos identidades, TokenCreator y Viewer a nivel de recurso."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from infra.bootstrap.apis import run
from infra.config.settings import ROOT, load


def emails(config, manifest):
    return {cid: config[spec['key']] + '@' + config['GCP_PROJECT_ID'] + '.iam.gserviceaccount.com'
            for cid, spec in manifest['accounts'].items()}


def expected_bindings(config, manifest, accounts):
    deployer = accounts['RS-SEC-002']
    bootstrap = config['BOOTSTRAP_ACCOUNT']
    member = ('serviceAccount:' if bootstrap.endswith('.gserviceaccount.com') else 'user:') + bootstrap
    bindings = [(email, manifest['viewer_role'], 'serviceAccount:' + deployer)
                for email in accounts.values()]
    bindings.append((deployer, manifest['token_role'], member))
    return bindings


def has_binding(policy, role, member):
    return any(binding['role'] == role and member in binding.get('members', [])
               and not binding.get('condition') for binding in policy.get('bindings', []))


def check_forbidden(policy, manifest, members=None):
    for binding in policy.get('bindings', []):
        if binding['role'] in manifest['forbidden_roles'] and (
                members is None or set(binding.get('members', [])) & members):
            raise RuntimeError('Binding amplio detectado: ' + binding['role'] + '; no se modifica automáticamente')


def manage(config, resources, manifest, mode):
    if set(manifest['accounts']) != {'RS-SEC-001', 'RS-SEC-002'}:
        raise ValueError('Solo se permiten las dos identidades catalogadas')
    accounts = emails(config, manifest)
    # Comprobar el rol antes de cualquier mutación, sin ampliar permisos si cambia.
    role = run(config, 'iam', 'roles', 'describe', manifest['viewer_role'])
    missing = set(manifest['viewer_permissions']) - set(role.get('includedPermissions', []))
    if missing:
        raise RuntimeError('Viewer no cubre: ' + ', '.join(sorted(missing)))
    print('[OK] Viewer cubre get y getIamPolicy', flush=True)
    existing = {account['email']: account for account in run(config, 'iam', 'service-accounts', 'list')}
    project_policy = run(config, 'projects', 'get-iam-policy', config['GCP_PROJECT_ID'])
    check_forbidden(project_policy, manifest, {'serviceAccount:' + email for email in accounts.values()})
    # Leer todas las políticas existentes antes de mutar.
    policies = {}
    for email in accounts.values():
        if email in existing:
            if existing[email].get('disabled'):
                raise RuntimeError('Cuenta deshabilitada: ' + email)
            policies[email] = run(config, 'iam', 'service-accounts', 'get-iam-policy', email)
            check_forbidden(policies[email], manifest)
    changes = 0
    for cid, email in accounts.items():
        spec = manifest['accounts'][cid]
        description = json.dumps(resources[cid]['labels'], sort_keys=True, separators=(',', ':'))
        if email not in existing:
            if mode != 'deploy':
                raise RuntimeError('Falta identidad ' + cid)
            run(config, 'iam', 'service-accounts', 'create', config[spec['key']],
                '--display-name=' + spec['display_name'], '--description=' + description)
            policies[email] = {}
            changes += 1
        elif existing[email].get('displayName') != spec['display_name'] or existing[email].get('description') != description:
            if mode != 'deploy':
                raise RuntimeError('Metadatos distintos para ' + cid)
            run(config, 'iam', 'service-accounts', 'update', email,
                '--display-name=' + spec['display_name'], '--description=' + description)
            changes += 1
        print('[OK] ' + cid + ' exists', flush=True)
    for email, role, member in expected_bindings(config, manifest, accounts):
        if not has_binding(policies[email], role, member):
            if mode != 'deploy':
                raise RuntimeError('Binding faltante: ' + role + ' sobre ' + email)
            run(config, 'iam', 'service-accounts', 'add-iam-policy-binding', email,
                '--member=' + member, '--role=' + role, '--condition=None')
            changes += 1
    print(json.dumps({'applied_changes': changes, 'mode': mode}), flush=True)
    # Validación real con la identidad impersonada: no se imprime ningún token.
    deployer_flag = '--impersonate-service-account=' + accounts['RS-SEC-002']
    for email in accounts.values():
        identity = run(config, 'iam', 'service-accounts', 'describe', email, deployer_flag)
        if identity.get('disabled') or identity.get('email') != email:
            raise RuntimeError('Identidad no válida: ' + email)
        policy = run(config, 'iam', 'service-accounts', 'get-iam-policy', email, deployer_flag)
        check_forbidden(policy, manifest)
        for target, role, member in expected_bindings(config, manifest, accounts):
            if target == email and not has_binding(policy, role, member):
                raise RuntimeError('Binding no confirmado: ' + role)
    print('[OK] IAM mínimo asignado e impersonación válida', flush=True)
    print('[OK] Sin roles amplios directos en cuentas ni Owner/Editor directos de identidades en proyecto', flush=True)
    print('[INFO] Privilegios heredados de organización/carpeta/grupos no certificados por esta comprobación')
    print(json.dumps({'changes': changes, 'mode': mode}), flush=True)
    return changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'config/dev.env')
    parser.add_argument('--manifest', type=Path, default=ROOT / 'infra/config/iam.json')
    parser.add_argument('--mode', choices=('deploy', 'validate'), default='validate')
    args = parser.parse_args()
    try:
        config, resources = load(args.config)
        manifest = json.loads(args.manifest.read_text())
        if manifest['viewer_role'] in manifest['forbidden_roles'] or manifest['token_role'] in manifest['forbidden_roles']:
            raise ValueError('Rol prohibido en manifiesto')
        manage(config, resources, manifest, args.mode)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
