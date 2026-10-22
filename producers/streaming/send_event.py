"""Productor CLI: un evento sintético validado hacia RS-STR-001."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from jsonschema import ValidationError
from contracts.streaming.validation import validate_event, validators
from infra.config.settings import ROOT, load
from producers.streaming.build_event import build_event, timestamp, utc_now
from producers.streaming.publish import PublicationError, check_operator, publish, target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--type', required=True, choices=sorted(validators()))
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--config', type=Path, default=ROOT / 'config/dev.env')
    args = parser.parse_args(argv)
    result = {'result': 'ERROR', 'mode': 'DRY_RUN' if args.dry_run else 'PUBLISH',
              'event_type': args.type, 'event_id': None, 'topic': None, 'message_id': None,
              'published': False, 'publication_uncertain': False}
    stage = 'CONFIGURATION'
    try:
        config, resources = load(args.config)
        result['topic'] = target(config, resources)
        stage = 'BUILD'
        event = build_event(args.type)
        result['event_id'] = event.get('event_id')
        result['event_timestamp'] = event.get('event_timestamp')
        stage = 'VALIDATE'
        validate_event(event)
        # La misma cadena, sin reconstruir ni alterar el hecho, llega al publicador.
        message = json.dumps(event, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        result['event'] = event
        if not args.dry_run:
            stage = 'OPERATOR'
            check_operator(config)
            stage = 'PUBLISH'
            result['message_id'] = publish(config, resources, message)
            result['published'] = True
        result['result'] = 'OK'
    except (OSError, ValueError, KeyError, RuntimeError, ValidationError, subprocess.TimeoutExpired) as error:
        result.update(stage=stage, error=str(error), publication_uncertain=
                      isinstance(error, PublicationError) and error.uncertain)
        print('[ERROR] ' + stage + ': ' + str(error), file=sys.stderr)
    result['timestamp'] = timestamp(utc_now())
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0 if result['result'] == 'OK' else 1


if __name__ == '__main__':
    sys.exit(main())
