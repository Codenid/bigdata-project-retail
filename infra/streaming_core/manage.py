"""Orquestación secuencial del Streaming Core catalogado."""
import argparse
import json
import signal
import subprocess
import sys
from pathlib import Path

from infra.bootstrap import apis
from infra.config.settings import ROOT, load
from infra.iam import manage as iam
from infra.pubsub import manage as pubsub
from infra.storage import manage as storage
from infra.bigquery import manage as bigquery

MODULES = (('IAM Foundation', iam, 'iam'), ('Pub/Sub', pubsub, 'pubsub'),
           ('Storage', storage, 'storage'), ('BigQuery', bigquery, 'bigquery'))


def manifest(name):
    return json.loads((ROOT / 'infra/config' / (name + '.json')).read_text())


def normalize(result):
    stats = dict(result) if isinstance(result, dict) else {'changes': result}
    stats['iam_changes'] = sum(stats.get(key, 0) for key in
                               ('iam_changes', 'project_iam_changes', 'dataset_iam_changes'))
    return stats


def orchestrate(mode, config_path, execute_destroy=False):
    if execute_destroy and mode != 'destroy':
        raise ValueError('--execute-destroy requiere destroy')
    context = {}
    results = []

    def configure(path):
        config, resources = load(path)
        manifests = {name: manifest(name) for name in ('apis', 'iam', 'pubsub', 'storage', 'bigquery')}
        if (not isinstance(manifests['apis'], list) or not manifests['apis'] or
                any(not isinstance(api, str) or not api.endswith('.googleapis.com') for api in manifests['apis'])):
            raise ValueError('Manifiesto de APIs inválido')
        context.update(config=config, resources=resources, manifests=manifests)
        return {'changes': 0}

    def invoke(module, name, operation, **kwargs):
        return module.manage(context['config'], context['resources'],
                             context['manifests'][name], operation, **kwargs)

    steps = [('Configuration', lambda: configure(config_path))]
    steps.append(('Bootstrap / APIs', lambda: apis.bootstrap(
        context['config'], context['manifests']['apis'], apply=mode == 'deploy')))
    steps.append(('IAM Foundation', lambda: invoke(iam, 'iam', 'deploy' if mode == 'deploy' else 'validate')))
    if mode == 'destroy':
        # Completar TODOS los previews protegidos antes de la primera eliminación.
        for label, module, name in reversed(MODULES[1:]):
            steps.append(('Precheck ' + label, lambda m=module, n=name: invoke(m, n, 'destroy')))
        if execute_destroy:
            for label, module, name in reversed(MODULES[1:]):
                steps.append(('Destroy ' + label, lambda m=module, n=name:
                              invoke(m, n, 'destroy', execute_destroy=True)))
    else:
        for label, module, name in MODULES[1:]:
            steps.append((label, lambda m=module, n=name: invoke(m, n, mode)))
    failed = False
    for label, action in steps:
        if failed:
            print('[SKIP] ' + label + ': dependencia anterior falló', flush=True)
            results.append({'step': label, 'status': 'SKIP'})
            continue
        try:
            stats = normalize(action())
            print(f"[OK] {label}: changes={stats.get('changes', 0)} iam_changes={stats['iam_changes']}", flush=True)
            results.append({'step': label, 'status': 'OK', **stats})
        except (Exception, KeyboardInterrupt) as error:
            failed = True
            print('[ERROR] ' + label + ': ' + str(error), file=sys.stderr, flush=True)
            results.append({'step': label, 'status': 'ERROR', 'error': str(error)})
    if mode == 'destroy':
        print('[SKIP] Eliminación de identidades, IAM Foundation, APIs, proyecto y billing: se conservan', flush=True)
    summary = {'mode': mode, 'success': not failed,
               'changes': sum(row.get('changes', 0) for row in results),
               'counts_complete': not failed,
               'iam_changes': sum(row.get('iam_changes', 0) for row in results), 'steps': results}
    if failed:
        print('[ERROR] Conteos parciales: el módulo fallido puede haber aplicado cambios; revisar su salida antes de reintentar', flush=True)
    print(json.dumps(summary, sort_keys=True), flush=True)
    print(('[ERROR]' if failed else '[OK]') + ' Resumen Streaming Core: ' +
          f"changes={summary['changes']} iam_changes={summary['iam_changes']}", flush=True)
    return 1 if failed else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'config/dev.env')
    parser.add_argument('--mode', choices=('deploy', 'validate', 'destroy'), required=True)
    parser.add_argument('--execute-destroy', action='store_true')
    args = parser.parse_args()
    if args.execute_destroy and args.mode != 'destroy':
        parser.error('--execute-destroy requiere --mode destroy')
    # SIGTERM permite ejecutar finally de los módulos; SIGKILL no es recuperable.
    def interrupted(signum, frame):
        raise KeyboardInterrupt('Interrumpido por señal ' + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    try:
        return orchestrate(args.mode, args.config, args.execute_destroy)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print('[ERROR] ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
