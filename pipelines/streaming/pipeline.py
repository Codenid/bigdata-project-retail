"""RS-STR-010/011: Pub/Sub -> validación -> GCS Bronze raw."""
import argparse
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path

import apache_beam as beam
from apache_beam.io import fileio
from apache_beam.options.pipeline_options import PipelineOptions, StandardOptions
from apache_beam.options.value_provider import StaticValueProvider
from apache_beam.pvalue import TaggedOutput
from apache_beam.transforms.window import FixedWindows
from jsonschema import ValidationError

from contracts.streaming.validation import validate_event
from infra.config.settings import ROOT, load

ERROR_TAG = 'invalid'


class ValidateAndRoute(beam.DoFn):
    """Conserva bytes válidos; preserva bytes inválidos sin filtrar el payload."""
    def process(self, raw):
        payload = raw if isinstance(raw, bytes) else str(raw).encode('utf-8')
        ingested = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        try:
            text = payload.decode('utf-8')
            event = json.loads(text)
            validate_event(event)
            event_date = event['event_timestamp'][:10]
            yield {'destination': f"event_type={event['event_type']}/event_date={event_date}",
                   'line': text}
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, KeyError, TypeError, ValueError) as error:
            # El error es categórico; no se registran payloads ni detalles de excepción.
            record = {'ingest_timestamp': ingested, 'error_type': type(error).__name__,
                      'payload_base64': base64.b64encode(payload).decode('ascii')}
            yield TaggedOutput(ERROR_TAG, {'destination': 'errors/ingest_date=' + ingested[:10],
                                            'line': json.dumps(record, sort_keys=True, separators=(',', ':'))})


class JsonLineSink(fileio.TextSink):
    def write(self, record):
        self._fh.write(record['line'].encode('utf-8'))
        self._fh.write(b'\n')


def write_partitioned(rows, output_path, temp_path, shards, label):
    return rows | label >> fileio.WriteToFiles(
        path=output_path, temp_directory=StaticValueProvider(str, temp_path),
        destination=lambda row: row['destination'], sink=lambda _: JsonLineSink(),
        file_naming=fileio.destination_prefix_naming(suffix='.jsonl'), shards=shards)


def build(pipeline, source, *, output_path, temp_path, window_seconds, shards):
    routed = (source
              | 'Fixed file windows' >> beam.WindowInto(FixedWindows(window_seconds))
              | 'Validate contracts' >> beam.ParDo(ValidateAndRoute()).with_outputs(ERROR_TAG, main='valid'))
    write_partitioned(routed.valid, output_path, temp_path + '/valid', shards, 'Write valid Bronze')
    write_partitioned(routed.invalid, output_path, temp_path + '/errors', shards, 'Write invalid evidence')
    return routed


def main(argv=None):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--config', type=Path, default=ROOT / 'config/dev.env')
    known, beam_args = parser.parse_known_args(argv)
    config, resources = load(known.config)
    for key in ('DATAFLOW_WINDOW_SECONDS', 'DATAFLOW_OUTPUT_SHARDS'):
        if os.environ.get(key):
            config[key] = os.environ[key]
    window_seconds = int(config['DATAFLOW_WINDOW_SECONDS'])
    shards = int(config['DATAFLOW_OUTPUT_SHARDS'])
    if not 60 <= window_seconds <= 3600 or not 1 <= shards <= 10:
        raise ValueError('Ventana 60..3600 segundos y shards 1..10')
    options = PipelineOptions(beam_args, save_main_session=True, streaming=True)
    options.view_as(StandardOptions).streaming = True
    subscription = f"projects/{config['GCP_PROJECT_ID']}/subscriptions/{resources['RS-STR-002']['name']}"
    bronze = 'gs://' + resources['RS-DATA-001']['name'] + '/streaming'
    temp = 'gs://' + resources['RS-STR-004']['name'] + '/fileio'
    with beam.Pipeline(options=options) as pipeline:
        source = pipeline | 'Read RS-STR-002' >> beam.io.ReadFromPubSub(subscription=subscription)
        build(pipeline, source, output_path=bronze, temp_path=temp,
              window_seconds=window_seconds, shards=shards)


if __name__ == '__main__':
    main()
