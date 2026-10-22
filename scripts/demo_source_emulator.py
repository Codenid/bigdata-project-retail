#!/usr/bin/env python3
"""Demo acotada del mismo engine de Streamlit; publicar exige --publish."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from infra.config.settings import load
from producers.emulator.engine import ProducerEngine
from producers.emulator.transport import OperatorPublisher


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish',action='store_true')
    parser.add_argument('--report',type=Path,default=Path('/tmp/retailsmart-source-emulator-demo.json'))
    args=parser.parse_args()
    if not args.publish:
        print('Plan: Estantería 1 evt/s × 5s; Tracking 1 evt/s × 5s; TELEMETRY_ANOMALY 4 muestras. Sin publicar. Usar --publish explícito.')
        return 0
    # Guard antes de publicar para evitar repetir accidentalmente esta demo.
    with args.report.open('x') as file:file.write('{}')
    result=dict(result='ERROR',started_at=datetime.now(timezone.utc).isoformat(),runs=[],records=[])
    engine=None
    try:
        config,resources=load(ROOT/'config/dev.env')
        transport=OperatorPublisher(config,resources)
        engine=ProducerEngine(config,resources,transport,max_run_seconds=5,lease_seconds=10)
        result['topic']=f"projects/{config['GCP_PROJECT_ID']}/topics/{resources['RS-STR-001']['name']}"
        for source in ('shelf','logistics'):
            engine.heartbeat();engine.set_rate(source,1)
            engine.start_source(source)
            time.sleep(5)
            engine.stop_source(source)
            snapshot=engine.snapshot()
            state=snapshot['sources'][source]
            result['runs'].append(dict(source=source,rate=1,window_seconds=5,
                success=state['success'],errors=state['errors'],status=state['status']))
            result['records']=snapshot['activity']
            args.report.write_text(json.dumps(result,indent=2)+'\n')
            print('[OK]',source,state['success'],'message_id confirmados;',state['errors'],'errores; STOP',flush=True)
            if state['errors'] or not state['success']:
                raise RuntimeError('Demo detenida por fallo de publicación; sin reintentos')
        engine.heartbeat();engine.set_scenario('TELEMETRY_ANOMALY');engine.set_rate('cold_room',1)
        engine.start_source('cold_room')
        # Ventana finita, sin polling ni consumidor.
        time.sleep(5)
        engine.stop_source('cold_room')
        snapshot=engine.snapshot()
        result['records']=snapshot['activity']
        state=snapshot['sources']['cold_room']
        values=[r['event']['payload']['value'] for r in reversed(result['records']) if r['source_id']=='cold_room']
        result['runs'].append(dict(source='cold_room',scenario='TELEMETRY_ANOMALY',rate=1,
            success=state['success'],errors=state['errors'],status=state['status'],values=values))
        if state['success']!=4 or state['errors'] or values!=[4.5,4.6,9,12]:
            raise RuntimeError('La evolución térmica no quedó completamente confirmada')
        if any(not r['message_id'] for r in result['records']):raise RuntimeError('Hay publicaciones no confirmadas')
        result['result']='OK'
        print('[OK] TELEMETRY_ANOMALY:',values,'cuatro message_id confirmados; STOP',flush=True)
    except Exception:
        result['error']='Demo detenida sin reintentos; revisar configuración, identidad, contratos o acceso pubsub.topics.publish.'
        print('[ERROR]',result['error'],file=sys.stderr,flush=True)
    finally:
        if engine:
            engine.close()
            result['workers_alive']=sum(bool(s.thread and s.thread.is_alive()) for s in engine.states.values())
        result['finished_at']=datetime.now(timezone.utc).isoformat()
        args.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    return 0 if result['result']=='OK' else 1


if __name__=='__main__':sys.exit(main())
