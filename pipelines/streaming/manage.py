"""Preflight, IAM, deploy, validate y stop de Streaming to Bronze."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from infra.config.settings import ROOT, load

ACTIVE = {'JOB_STATE_PENDING', 'JOB_STATE_QUEUED', 'JOB_STATE_RUNNING',
          'JOB_STATE_DRAINING', 'JOB_STATE_CANCELLING', 'JOB_STATE_UPDATED'}
REQUIRED = ('DATAFLOW_JOB_NAME', 'DATAFLOW_NUM_WORKERS', 'DATAFLOW_MAX_WORKERS',
            'DATAFLOW_MACHINE_TYPE', 'DATAFLOW_MACHINE_VCPUS',
            'DATAFLOW_MACHINE_MEMORY_GIB', 'DATAFLOW_DISK_GB',
            'DATAFLOW_WINDOW_SECONDS', 'DATAFLOW_OUTPUT_SHARDS',
            'DATAFLOW_ESTIMATED_HOURS')


def run(config, *args):
    command = ['gcloud', *args, '--account=' + config['BOOTSTRAP_ACCOUNT'],
               '--project=' + config['GCP_PROJECT_ID'], '--quiet', '--format=json']
    env = dict(os.environ, CLOUDSDK_CORE_PROJECT=config['GCP_PROJECT_ID'],
               CLOUDSDK_COMPUTE_REGION=config['GCP_REGION'])
    result = subprocess.run(command, capture_output=True, text=True, timeout=180, env=env)
    if result.stderr:
        print(result.stderr, file=sys.stderr, end='')
    if result.returncode:
        raise RuntimeError('gcloud ' + ' '.join(args[:3]) + f' falló ({result.returncode})')
    return json.loads(result.stdout or 'null')


def identities(config):
    suffix = '@' + config['GCP_PROJECT_ID'] + '.iam.gserviceaccount.com'
    return (config['DATAFLOW_SERVICE_ACCOUNT_ID'] + suffix,
            config['DEPLOYER_SERVICE_ACCOUNT_ID'] + suffix)


def validate_config(config, resources, manifest):
    missing = [key for key in REQUIRED if not config.get(key)]
    if missing:
        raise ValueError('Falta configuración Dataflow: ' + ', '.join(missing))
    if manifest['components'] != ['RS-STR-010', 'RS-STR-011']:
        raise ValueError('Componentes fuera del Bloque C')
    if config['GCP_REGION'] != 'us-central1':
        raise ValueError('El pricing aprobado corresponde a us-central1')
    if not re.fullmatch(r'[a-z]([-a-z0-9]{0,38}[a-z0-9])?', config['DATAFLOW_JOB_NAME']):
        raise ValueError('DATAFLOW_JOB_NAME inválido')
    workers, maximum = int(config['DATAFLOW_NUM_WORKERS']), int(config['DATAFLOW_MAX_WORKERS'])
    if workers != 1 or maximum != 1:
        raise ValueError('Este corte de costo exige exactamente un worker')
    if config['DATAFLOW_MACHINE_TYPE'] != 'n1-standard-1':
        raise ValueError('Machine type fuera del corte de costo aprobado')
    if (config['DATAFLOW_MACHINE_VCPUS'], config['DATAFLOW_MACHINE_MEMORY_GIB'],
            config['DATAFLOW_DISK_GB']) != ('1', '3.75', '400'):
        raise ValueError('Perfil de costo n1-standard-1 inconsistente')
    if not 0 < float(config['DATAFLOW_ESTIMATED_HOURS']) <= 24:
        raise ValueError('DATAFLOW_ESTIMATED_HOURS debe estar entre 0 y 24')
    if not 60 <= int(config['DATAFLOW_WINDOW_SECONDS']) <= 3600:
        raise ValueError('DATAFLOW_WINDOW_SECONDS fuera de rango')
    if not 1 <= int(config['DATAFLOW_OUTPUT_SHARDS']) <= 10:
        raise ValueError('DATAFLOW_OUTPUT_SHARDS fuera de rango')
    if resources['RS-DATA-001']['location'] not in ('configurable', config['GCP_REGION']):
        raise ValueError('Bronze incompatible con región Dataflow')


def estimate(config, manifest):
    price = manifest['pricing_us_central1']
    hours = float(config['DATAFLOW_ESTIMATED_HOURS'])
    hourly = (float(config['DATAFLOW_MACHINE_VCPUS']) * price['streaming_vcpu_hour_usd'] +
              float(config['DATAFLOW_MACHINE_MEMORY_GIB']) * price['memory_gib_hour_usd'] +
              float(config['DATAFLOW_DISK_GB']) * price['standard_pd_gib_hour_usd'])
    return {'hourly_usd': round(hourly, 4), 'planned_hours': hours,
            'estimated_worker_usd': round(hourly * hours, 4),
            'excludes': ['Pub/Sub volume', 'Cloud Storage', 'Cloud Logging', 'network']}


def member_in(policy, role, member):
    return any(row.get('role') == role and member in row.get('members', [])
               and not row.get('condition') for row in policy.get('bindings', []))


def binding_specs(config, resources, manifest):
    runtime, launcher = identities(config)
    return [
        ('project', config['GCP_PROJECT_ID'], manifest['runtime_project_role'], 'serviceAccount:' + runtime),
        ('subscription', resources['RS-STR-002']['name'], manifest['runtime_subscription_role'], 'serviceAccount:' + runtime),
        ('bucket', resources['RS-DATA-001']['name'], manifest['runtime_bucket_role'], 'serviceAccount:' + runtime),
        ('bucket', resources['RS-STR-004']['name'], manifest['runtime_bucket_role'], 'serviceAccount:' + runtime),
        ('project', config['GCP_PROJECT_ID'], manifest['launcher_project_role'], 'serviceAccount:' + launcher),
        ('service-account', runtime, manifest['launcher_runtime_role'], 'serviceAccount:' + launcher),
        ('bucket', resources['RS-STR-004']['name'], manifest['launcher_staging_role'], 'serviceAccount:' + launcher),
    ]


def policy(config, scope, target):
    if scope == 'project':
        return run(config, 'projects', 'get-iam-policy', target)
    if scope == 'subscription':
        return run(config, 'pubsub', 'subscriptions', 'get-iam-policy', target)
    if scope == 'bucket':
        return run(config, 'storage', 'buckets', 'get-iam-policy', 'gs://' + target)
    return run(config, 'iam', 'service-accounts', 'get-iam-policy', target)


def add_binding(config, scope, target, role, member):
    if scope == 'project':
        run(config, 'projects', 'add-iam-policy-binding', target, '--role=' + role, '--member=' + member, '--condition=None')
    elif scope == 'subscription':
        run(config, 'pubsub', 'subscriptions', 'add-iam-policy-binding', target, '--role=' + role, '--member=' + member)
    elif scope == 'bucket':
        run(config, 'storage', 'buckets', 'add-iam-policy-binding', 'gs://' + target, '--role=' + role, '--member=' + member)
    else:
        run(config, 'iam', 'service-accounts', 'add-iam-policy-binding', target, '--role=' + role, '--member=' + member, '--condition=None')


def preflight(config, resources, manifest):
    enabled = {row['config']['name'] for row in run(config, 'services', 'list', '--enabled')}
    required_apis = {'dataflow.googleapis.com', 'compute.googleapis.com', 'pubsub.googleapis.com', 'storage.googleapis.com'}
    if required_apis - enabled:
        raise RuntimeError('APIs faltantes: ' + ', '.join(sorted(required_apis - enabled)))
    runtime, launcher = identities(config)
    for email in (runtime, launcher):
        if run(config, 'iam', 'service-accounts', 'describe', email).get('disabled'):
            raise RuntimeError('Identidad deshabilitada: ' + email)
    sub = run(config, 'pubsub', 'subscriptions', 'describe', resources['RS-STR-002']['name'])
    if not sub.get('name', '').endswith('/' + resources['RS-STR-002']['name']):
        raise RuntimeError('RS-STR-002 no disponible')
    for cid in ('RS-DATA-001', 'RS-STR-004'):
        bucket = run(config, 'storage', 'buckets', 'describe', 'gs://' + resources[cid]['name'])
        if bucket.get('location', '').lower() != config['GCP_REGION']:
            raise RuntimeError(cid + ' fuera de región')
    quotas = run(config, 'compute', 'regions', 'describe', config['GCP_REGION']).get('quotas', [])
    cpu = next((q for q in quotas if q.get('metric') == 'CPUS'), None)
    needed = int(config['DATAFLOW_MAX_WORKERS']) * int(config['DATAFLOW_MACHINE_VCPUS'])
    if not cpu or float(cpu['limit']) - float(cpu['usage']) < needed:
        raise RuntimeError(f'Cuota CPU insuficiente; se requieren {needed} vCPU libres')
    jobs = run(config, 'dataflow', 'jobs', 'list', '--region=' + config['GCP_REGION']) or []
    active = [job for job in jobs if job.get('state') in ACTIVE]
    own = [job for job in active if job.get('name') == config['DATAFLOW_JOB_NAME']]
    foreign = [job for job in active if job.get('name') != config['DATAFLOW_JOB_NAME']]
    if foreign or len(own) > manifest['active_job_limit']:
        raise RuntimeError('Existe otro job Dataflow activo; límite de costo alcanzado')
    print('[OK] APIs, recursos, identidades y cuota CPU verificados')
    print(json.dumps({'active_jobs': len(active), 'free_cpu_quota': float(cpu['limit']) - float(cpu['usage']),
                      'cost_estimate': estimate(config, manifest)}, sort_keys=True))
    return own


def reconcile_iam(config, resources, manifest, apply=False):
    missing = []
    for spec in binding_specs(config, resources, manifest):
        scope, target, role, member = spec
        if not member_in(policy(config, scope, target), role, member):
            missing.append(spec)
    if apply:
        for spec in missing:
            add_binding(config, *spec)
        missing = [spec for spec in binding_specs(config, resources, manifest)
                   if not member_in(policy(config, spec[0], spec[1]), spec[2], spec[3])]
    print(json.dumps({'iam_missing': [{'scope': s, 'target': t, 'role': r} for s, t, r, _ in missing],
                      'apply': apply}, sort_keys=True))
    if missing and apply:
        raise RuntimeError('IAM runtime no quedó confirmado')
    return missing


def launch(config, resources):
    runtime, launcher = identities(config)
    staging = 'gs://' + resources['RS-STR-004']['name']
    command = [sys.executable, '-m', 'pipelines.streaming.pipeline',
               '--config=' + str(ROOT / 'config/dev.env'), '--runner=DataflowRunner',
               '--project=' + config['GCP_PROJECT_ID'], '--region=' + config['GCP_REGION'],
               '--job_name=' + config['DATAFLOW_JOB_NAME'], '--temp_location=' + staging + '/temp',
               '--staging_location=' + staging + '/staging', '--service_account_email=' + runtime,
               '--impersonate_service_account=' + launcher,
               '--num_workers=1', '--max_num_workers=1', '--autoscaling_algorithm=NONE',
               '--machine_type=' + config['DATAFLOW_MACHINE_TYPE'],
               '--disk_size_gb=' + config['DATAFLOW_DISK_GB'], '--setup_file=' + str(ROOT / 'setup.py')]
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode:
        raise RuntimeError('El lanzamiento Dataflow falló')


def manage(config, resources, manifest, mode, execute_dataflow=False, execute_stop=False):
    validate_config(config, resources, manifest)
    active = preflight(config, resources, manifest) if mode != 'stop' else run(
        config, 'dataflow', 'jobs', 'list', '--region=' + config['GCP_REGION']) or []
    if mode == 'stop':
        targets = [job for job in active if job.get('name') == config['DATAFLOW_JOB_NAME'] and job.get('state') in ACTIVE]
        print(json.dumps({'stop': [job['id'] for job in targets], 'execute': execute_stop}))
        if execute_stop:
            for job in targets:
                run(config, 'dataflow', 'jobs', 'cancel', job['id'], '--region=' + config['GCP_REGION'])
        return
    missing = reconcile_iam(config, resources, manifest, apply=execute_dataflow)
    if mode == 'validate':
        if missing:
            raise RuntimeError('IAM runtime pendiente')
        print('[OK] Pipeline preparado; job activo=' + str(bool(active)).lower())
        return
    if not execute_dataflow:
        print('[SKIP] Preview completado; use --execute-dataflow solo con aprobación de costo')
        return
    if active:
        print('[OK] Job Dataflow ya activo; no se crea duplicado')
        return
    launch(config, resources)
    print('[OK] Solicitud de job Dataflow enviada')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'config/dev.env')
    parser.add_argument('--manifest', type=Path, default=ROOT / 'infra/config/dataflow.json')
    parser.add_argument('--mode', choices=('deploy', 'validate', 'stop'), default='validate')
    parser.add_argument('--execute-dataflow', action='store_true')
    parser.add_argument('--execute-stop', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.execute_dataflow and args.mode != 'deploy':
            raise ValueError('--execute-dataflow requiere --mode deploy')
        if args.execute_stop and args.mode != 'stop':
            raise ValueError('--execute-stop requiere --mode stop')
        config, resources = load(args.config)
        for key in REQUIRED:
            if os.environ.get(key):
                config[key] = os.environ[key]
        manage(config, resources, json.loads(args.manifest.read_text()), args.mode,
               args.execute_dataflow, args.execute_stop)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
