"""CLI de perfiles pequeños: dry-run predeterminado; publish solo explícito."""
import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys

from jsonschema import ValidationError
from infra.config.settings import ROOT, load
from producers.streaming.publish import PublicationError, check_operator, publish, target
from producers.streaming.scenarios import build_plan, definitions, serialize_plan, timestamp


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', required=True, choices=tuple(definitions()['profiles']))
    parser.add_argument('--run-id')
    parser.add_argument('--start-time')
    parser.add_argument('--config', type=Path, default=ROOT / 'config/dev.env')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--dry-run', action='store_true')
    modes.add_argument('--publish', action='store_true')
    args = parser.parse_args(argv)
    if args.publish and (args.run_id is None or args.start_time is None):
        parser.error('--publish requiere --run-id y --start-time explícitos')
    result = {'result': 'ERROR', 'mode': 'PUBLISH' if args.publish else 'DRY_RUN',
              'scenario': args.scenario, 'topic': None, 'validated_count': 0,
              'confirmed_count': 0, 'records': []}
    stage = 'CONFIGURATION'
    try:
        config, resources = load(args.config)
        result['topic'] = target(config, resources)
        stage = 'BUILD'
        plan = build_plan(args.scenario, args.run_id, args.start_time)
        stage = 'VALIDATE'
        messages = serialize_plan(plan)
        # Reporte a partir de las mismas cadenas validadas que recibiría el adaptador.
        events = [json.loads(message) for message in messages]
        result.update(run_id=plan.run_id, start_time=timestamp(plan.start_time),
                      profile_version=plan.version, description=plan.profile['description'],
                      verticals=plan.profile['verticals'], validated_count=len(messages),
                      counts_by_type=dict(sorted(Counter(e['event_type'] for e in events).items())),
                      events=events)
        result['records'] = [{'index': index, 'event_type': event['event_type'],
                              'event_id': event['event_id'], 'event_timestamp': event['event_timestamp'],
                              'message_id': None, 'status': 'PENDING' if args.publish else 'VALIDATED'}
                             for index, event in enumerate(events)]
        if args.publish:
            stage = 'OPERATOR'
            check_operator(config)
            stage = 'PUBLISH'
            for record, message in zip(result['records'], messages):
                try:
                    record['message_id'] = publish(config, resources, message)
                except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired, KeyboardInterrupt) as error:
                    uncertain = error.uncertain if isinstance(error, PublicationError) else True
                    record.update(status='UNCERTAIN' if uncertain else 'ERROR', error=str(error))
                    raise
                record['status'] = 'OK'
                result['confirmed_count'] += 1
        result['result'] = 'OK'
    except (OSError, ValueError, KeyError, RuntimeError, ValidationError,
            subprocess.TimeoutExpired, KeyboardInterrupt) as error:
        result.update(stage=stage, error=str(error))
        print('[ERROR] ' + stage + ': ' + str(error), file=sys.stderr)
    result['pending_count'] = sum(record['status'] == 'PENDING' for record in result['records'])
    result['uncertain_count'] = sum(record['status'] == 'UNCERTAIN' for record in result['records'])
    print(json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False))
    return 0 if result['result'] == 'OK' else 1


if __name__ == '__main__':
    sys.exit(main())
