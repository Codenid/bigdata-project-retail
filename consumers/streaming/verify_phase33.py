"""Comparación local con evidencia publicada; no tiene acceso a GCP."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from uuid import UUID

MANIFEST = Path(__file__).resolve().parents[1] / 'tests/fixtures/phase33-expected.json'


def content_hash(event):
    encoded = json.dumps(event, sort_keys=True, ensure_ascii=False,
                         allow_nan=False, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def load_manifest():
    manifest = json.loads(MANIFEST.read_text())
    rows = manifest['events']
    if len(rows) != 46 or len({r['event_id'] for r in rows}) != 46 or len({r['message_id'] for r in rows}) != 46:
        raise ValueError('Manifiesto Fase 3.3 inválido')
    for row in rows:
        UUID(row['event_id'])
        if not isinstance(row['message_id'], str) or not row['message_id'].isdigit() or not re.fullmatch(r'[a-f0-9]{64}', row['sha256']):
            raise ValueError('Identificador/hash de manifiesto inválido')
    return manifest


def match(event, message_id, manifest):
    expected = next((row for row in manifest['events'] if row['event_id'] == event['event_id']), None)
    if expected is None:
        # Un message_id histórico con otro event_id también es conflicto.
        return 'CONFLICT' if any(row['message_id'] == message_id for row in manifest['events']) else 'FOREIGN'
    checks = (expected['message_id'] == message_id,
              expected['event_type'] == event['event_type'],
              expected['event_timestamp'] == event['event_timestamp'],
              expected['schema_version'] == event['schema_version'],
              expected['sha256'] == content_hash(event))
    return 'EXPECTED' if all(checks) else 'CONFLICT'


def summarize(records, manifest):
    expected = {row['event_id'] for row in manifest['events']}
    found = {row['event_id'] for row in records if row['validation'] == 'VALID' and row['phase33'] == 'EXPECTED'}
    missing = sorted(expected - found)
    return dict(state='COMPLETE' if found == expected else 'PARTIAL' if found else 'UNAVAILABLE',
                expected_total=len(expected), expected_found=len(found), expected_missing=len(missing),
                missing_event_ids=missing,
                expected_by_type=dict(sorted(Counter(row['event_type'] for row in manifest['events']).items())),
                found_by_type=dict(sorted(Counter(next(r['event_type'] for r in manifest['events'] if r['event_id'] == event_id) for event_id in found).items())))


def combine_reports(reports, manifest):
    """Consolidar evidencia local; nunca autoriza ni ejecuta ACK."""
    records = []
    for report in reports:
        for original in report['records']:
            row = dict(original)
            if row['validation'] == 'VALID':
                expected = next((r for r in manifest['events'] if r['event_id'] == row['event_id']), None)
                if expected:
                    fields = ('message_id', 'event_type', 'event_timestamp', 'schema_version')
                    row['phase33'] = 'EXPECTED' if all(row.get(k) == expected[k] for k in fields) and row.get('content_sha256') == expected['sha256'] else 'CONFLICT'
                else:
                    row['phase33'] = 'FOREIGN'
            records.append(row)
    seen, duplicates = {}, 0
    for row in records:
        if row['validation'] != 'VALID':
            continue
        identity = (row['message_id'], row.get('content_sha256'))
        previous = seen.setdefault(row['event_id'], [])
        duplicates += any(old_identity == identity for old_identity, _ in previous)
        if any(old_identity != identity for old_identity, _ in previous):
            row['phase33'] = 'CONFLICT'
            for _, old in previous:
                old['phase33'] = 'CONFLICT'
        previous.append((identity, row))
    result = summarize(records, manifest)
    result.update(deliveries=len(records), duplicates=duplicates,
                  conflicts=sum(r['phase33'] == 'CONFLICT' for r in records))
    return result


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description='Consolidación offline de reportes locales; sin GCP ni ACK')
    parser.add_argument('reports', nargs='+', type=Path)
    args = parser.parse_args(argv)
    reports = [json.loads(path.read_text()) for path in args.reports]
    print(json.dumps(combine_reports(reports, load_manifest()), sort_keys=True))


if __name__ == '__main__':
    main()
