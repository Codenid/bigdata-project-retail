"""FASE 2.1: preflight y habilitación idempotente de APIs; no crea recursos IAM."""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from infra.config.settings import ROOT, load


def run(config, *args):
    command = ['gcloud', *args, '--account', config['BOOTSTRAP_ACCOUNT'], '--quiet', '--format=json']
    # Los roles predefinidos son globales: --project los convierte en una consulta inválida.
    if args[:3] != ('iam', 'roles', 'describe') or not args[3].startswith('roles/'):
        command.extend(['--project', config['GCP_PROJECT_ID']])
    session = os.environ.copy()
    session.update(CLOUDSDK_CORE_PROJECT=config['GCP_PROJECT_ID'],
                   CLOUDSDK_COMPUTE_REGION=config['GCP_REGION'])
    result = subprocess.run(command, text=True, capture_output=True, timeout=180, env=session)
    if result.stderr:
        print(result.stderr, file=sys.stderr, end='')
    if result.returncode:
        raise RuntimeError(f'gcloud {args[0]} {args[1]} falló (código {result.returncode})')
    return json.loads(result.stdout or 'null')


def bootstrap(config, apis, apply=False):
    if not shutil.which('gcloud'):
        raise RuntimeError('gcloud no está instalado o no está en PATH')
    accounts = run(config, 'auth', 'list', '--filter=status:ACTIVE')
    if not any(account.get('account') == config['BOOTSTRAP_ACCOUNT'] for account in accounts):
        raise RuntimeError('BOOTSTRAP_ACCOUNT no coincide con la cuenta activa; autenticar/activar con gcloud')
    print('OK: cuenta activa coincide con BOOTSTRAP_ACCOUNT', flush=True)
    project = run(config, 'projects', 'describe', config['GCP_PROJECT_ID'])
    if project.get('projectId') != config['GCP_PROJECT_ID'] or project.get('lifecycleState') != 'ACTIVE':
        raise RuntimeError('Proyecto no coincide o no está ACTIVE')
    billing = run(config, 'billing', 'projects', 'describe', config['GCP_PROJECT_ID'])
    if billing.get('billingEnabled') is not True:
        raise RuntimeError('El proyecto no tiene facturación habilitada')
    def enabled():
        return {service['config']['name'] for service in
                run(config, 'services', 'list', '--enabled')}
    missing = sorted(set(apis) - enabled())
    changes = len(missing) if apply else 0
    print(json.dumps({'missing_apis': missing, 'apply': apply}), flush=True)
    if missing and apply:
        # Se habilitan únicamente las APIs faltantes del manifiesto externo.
        run(config, 'services', 'enable', *missing)
        missing = sorted(set(apis) - enabled())
    if missing:
        raise RuntimeError('APIs pendientes: ' + ', '.join(missing))
    print('[OK] Bootstrap / APIs válido')
    return {'changes': changes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'config/dev.env')
    parser.add_argument('--apis', type=Path, default=ROOT / 'infra/config/apis.json')
    parser.add_argument('--mode', choices=('config', 'plan', 'validate', 'deploy'), default='config')
    args = parser.parse_args()
    try:
        config, resources = load(args.config)
        apis = json.loads(args.apis.read_text())
        if not isinstance(apis, list) or not apis or any(
                not isinstance(api, str) or not api.endswith('.googleapis.com') for api in apis):
            raise ValueError('Manifiesto de APIs inválido')
        if args.mode in ('config', 'plan'):
            print(json.dumps({'resources': resources, 'apis': apis}, indent=2))
            print('OK: configuración válida; sin llamadas GCP.')
        else:
            bootstrap(config, apis, apply=args.mode == 'deploy')
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
