"""Inspección puntual de RS-STR-002; ACK restringido a evidencia de Fase 3.3."""
import argparse
import base64
import binascii
import json
from pathlib import Path
import subprocess
import sys

from jsonschema import ValidationError
from contracts.streaming.validation import validate_event
from infra.config.settings import ROOT, load
from consumers.streaming.pubsub import Client, target
from consumers.streaming.verify_phase33 import content_hash, load_manifest, match, summarize


def limit_value(value):
    number = int(value)
    if not 1 <= number <= 50:
        raise argparse.ArgumentTypeError('--limit debe estar entre 1 y 50')
    return number


def reject_constant(_):
    raise ValueError('Constante JSON no finita')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Clave JSON duplicada')
        result[key] = value
    return result


def inspect(rows, manifest=None):
    records, candidates, seen = [], [], {}
    # Validar el lote completo antes de seleccionar cualquier ACK: detecta conflictos tardíos.
    for row in rows:
        record = dict(message_id=None, event_id=None, event_type=None, event_timestamp=None,
                      schema_version=None, validation='INVALID', ack_status='INVALID',
                      phase33='NOT_CHECKED', duplicate=False)
        records.append(record)
        try:
            if not isinstance(row, dict) or not isinstance(row.get('message'), dict):
                raise ValueError('Estructura Pub/Sub inválida')
            message = row['message']
            mid = message.get('messageId')
            if not isinstance(mid, str) or not mid.isdigit() or len(mid) > 64:
                raise ValueError('message_id inválido')
            record['message_id'] = mid
            raw = base64.b64decode(message['data'], validate=True).decode('utf-8', errors='strict')
            event = json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)
            validate_event(event)
            record.update({field: event[field] for field in ('event_id', 'event_type', 'event_timestamp', 'schema_version')})
            record.update(validation='VALID', ack_status='NOT_ACKED', content_sha256=content_hash(event))
            record['phase33'] = match(event, mid, manifest) if manifest else 'NOT_CHECKED'
            identity = (mid, record['content_sha256'])
            previous = seen.setdefault(event['event_id'], [])
            record['duplicate'] = any(old_identity == identity for old_identity, _ in previous)
            if any(old_identity != identity for old_identity, _ in previous):
                record['phase33'] = 'CONFLICT'
                for _, old in previous:
                    old['phase33'] = 'CONFLICT'
            previous.append((identity, record))
            ack_id = row.get('ackId')
            if record['phase33'] == 'EXPECTED':
                if isinstance(ack_id, str) and ack_id:
                    candidates.append((record, ack_id))
                else:
                    record['error'] = 'ACK_HANDLE_MISSING'
        except (ValueError, KeyError, TypeError, UnicodeError, binascii.Error, ValidationError, RecursionError):
            record['error'] = 'DECODE_JSON_OR_CONTRACT_INVALID'
    # Un message_id no puede corresponder a dos eventos distintos del mismo lote.
    by_message = {}
    for record in records:
        if record['validation'] == 'VALID':
            previous = by_message.setdefault(record['message_id'], [])
            if any(old['event_id'] != record['event_id'] for old in previous):
                record['phase33'] = 'CONFLICT'
                for old in previous:
                    old['phase33'] = 'CONFLICT'
            previous.append(record)
    return records, [(record, aid) for record, aid in candidates if record['phase33'] == 'EXPECTED']


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=limit_value, default=10)
    parser.add_argument('--verify-phase33', action='store_true')
    parser.add_argument('--ack', action='store_true')
    parser.add_argument('--config', type=Path, default=ROOT / 'config/dev.env')
    args = parser.parse_args(argv)
    if args.ack and not args.verify_phase33:
        parser.error('--ack requiere --verify-phase33; no se permite drenar mensajes arbitrarios')
    result = dict(result='ERROR', mode='CONTROLLED_ACK' if args.ack else 'INSPECTION',
                  subscription=None, limit=args.limit, records=[], acked=0, ack_uncertain=False)
    stage = 'CONFIGURATION'
    try:
        config, resources = load(args.config)
        result['subscription'] = target(config, resources)
        manifest = load_manifest() if args.verify_phase33 else None
        if manifest and manifest['topic'] != f"projects/{config['GCP_PROJECT_ID']}/topics/{resources['RS-STR-001']['name']}":
            raise ValueError('El manifiesto no pertenece al destino configurado')
        stage = 'OPERATOR'
        client = Client(config, resources)
        result['operator_verified'] = True
        stage = 'ACCESS'
        client.check_access()
        result['access_checked'] = True
        stage = 'PULL'
        records, candidates = inspect(client.pull(args.limit), manifest)
        result['records'] = records
        result.update(retrieved=len(records), valid=sum(r['validation'] == 'VALID' for r in records),
                      invalid=sum(r['validation'] == 'INVALID' for r in records),
                      duplicates=sum(r['duplicate'] for r in records),
                      conflicts=sum(r['phase33'] == 'CONFLICT' for r in records),
                      foreign=sum(r['phase33'] == 'FOREIGN' for r in records))
        if manifest:
            result['phase33'] = summarize(records, manifest)
        if args.ack and candidates:
            stage = 'ACK'
            result['ack_uncertain'] = True
            client.acknowledge([aid for _, aid in candidates])
            result['ack_uncertain'] = False
            for record, _ in candidates:
                record['ack_status'] = 'ACKED'
            result['acked'] = len(candidates)
        result['result'] = 'ERROR' if result['invalid'] or result['conflicts'] or any('error' in r for r in records) else 'OK'
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.TimeoutExpired):
        # No publicar excepciones arbitrarias: pueden contener token, ackId o datos recibidos.
        result.update(stage=stage, error='OPERATION_FAILED_' + stage)
        print('[ERROR] ' + stage + ': operación detenida sin reintentos ni cambios IAM. '
              + ('Verificar pubsub.subscriptions.consume sobre RS-STR-002.' if stage in ('ACCESS', 'PULL') else 'Revisar configuración/identidad o respuesta de la operación.'), file=sys.stderr)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True))
    return 0 if result['result'] == 'OK' else 1


if __name__ == '__main__':
    sys.exit(main())
