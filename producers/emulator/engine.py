"""Engine acotado por fuente, reloj monotónico y parada cooperativa."""
import atexit
from collections import deque
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
import os
import threading
import time
from uuid import uuid4
import weakref

from contracts.streaming.validation import validate_event
from producers.streaming.build_event import build_event
from producers.streaming.publish import publish
from producers.streaming.scenarios import build_plan, serialize_plan
from producers.emulator.sources import BY_ID, SOURCES, compatible


@dataclass
class State:
    rate: float = 1
    running: bool = False
    produced: int = 0
    success: int = 0
    errors: int = 0
    last_event_id: str = ''
    last_message_id: str = ''
    last_event_time: str = ''
    reason: str = ''
    cursor: int = 0
    last_started: float = float('-inf')
    stop: threading.Event = field(default_factory=threading.Event)
    wake: threading.Event = field(default_factory=threading.Event)
    io: threading.Lock = field(default_factory=threading.Lock)
    thread: object = None
    samples: deque = field(default_factory=lambda:deque(maxlen=50))


class ProducerEngine:
    def __init__(self, config, resources, transport, *, max_rate=None,
                 max_run_seconds=None, lease_seconds=None):
        self.config, self.resources, self.transport = dict(config), deepcopy(resources), transport
        self.max_rate = float(max_rate if max_rate is not None else config.get('EMULATOR_MAX_RATE',os.getenv('EMULATOR_MAX_RATE','20')))
        self.max_run_seconds = float(max_run_seconds if max_run_seconds is not None else config.get('EMULATOR_MAX_RUN_SECONDS',os.getenv('EMULATOR_MAX_RUN_SECONDS','300')))
        self.lease_seconds = float(lease_seconds if lease_seconds is not None else config.get('EMULATOR_LEASE_SECONDS',os.getenv('EMULATOR_LEASE_SECONDS','5')))
        if not (0.1 <= self.max_rate <= 20 and 0 < self.max_run_seconds <= 300 and 0 < self.lease_seconds <= 10):
            raise ValueError('Límites: MAX_RATE≤20, MAX_RUN_SECONDS≤300, LEASE_SECONDS≤10; todos positivos')
        self.states = {source.id:State(rate=min(1,self.max_rate)) for source in SOURCES}
        self.lock = threading.RLock()
        self.activity = deque(maxlen=50)
        self.scenario = None
        self._plan = None
        self._closed = False
        self._heartbeat = time.monotonic()
        self._created = self._heartbeat
        self._started = None
        reference = weakref.ref(self)
        def shutdown():
            engine = reference()
            if engine:
                engine.close()
        atexit.register(shutdown)

    def heartbeat(self):
        with self.lock:
            if not self._closed:
                self._heartbeat = time.monotonic()

    def _check(self, source_id):
        if self._closed:
            raise RuntimeError('Engine cerrado; reconectar')
        if source_id not in self.states:
            raise ValueError('Fuente desconocida')
        if not compatible(source_id,self.scenario):
            raise ValueError('Fuente incompatible con el escenario seleccionado')
        if time.monotonic()-self._heartbeat >= self.lease_seconds:
            raise RuntimeError('Sesión inactiva; actualizar conexión antes de iniciar')

    def set_scenario(self, scenario):
        from producers.streaming.scenarios import definitions
        with self.lock:
            if any(s.running or (s.thread and s.thread.is_alive()) for s in self.states.values()):
                raise RuntimeError('Detener todas las fuentes antes de cambiar escenario')
            if scenario is not None and scenario not in definitions()['profiles']:
                raise ValueError('Escenario desconocido')
            self.scenario, self._plan = scenario, None
            for state in self.states.values():
                state.cursor = 0

    def set_rate(self, source_id, rate):
        rate = float(rate)
        if not math.isfinite(rate) or not 0.1 <= rate <= self.max_rate:
            raise ValueError(f'Rate debe ser mayor a 0 y máximo {self.max_rate:g} evt/s')
        with self.lock:
            self.states[source_id].rate = rate
            self.states[source_id].wake.set()

    def _prepare(self, force=False):
        if self.scenario is not None and (self._plan is None or force):
            now = datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
            plan = build_plan(self.scenario, 'emulator-'+str(uuid4()), now)
            messages = serialize_plan(plan)  # Plan íntegro antes de iniciar cualquier fuente.
            self._plan = [json.loads(message) for message in messages]
            for state in self.states.values():
                state.cursor = 0

    def start_source(self, source_id):
        with self.lock:
            self._check(source_id)
            state = self.states[source_id]
            if state.running:
                return
            if state.thread and state.thread.is_alive():
                raise RuntimeError('Publicación anterior aún en curso')
            self._prepare(force=not any(s.running for s in self.states.values()))
            state.stop.clear(); state.wake.clear()
            state.running, state.reason = True, ''
            if self._started is None:
                self._started = time.monotonic()
            state.thread = threading.Thread(target=self._worker, args=(source_id,),
                name='retailsmart-'+source_id, daemon=True)
            state.thread.start()

    def start_all(self):
        started = []
        try:
            with self.lock:
                for source in SOURCES:
                    if compatible(source.id,self.scenario):
                        self.start_source(source.id)
                        started.append(source.id)
        except Exception:
            for source_id in started:
                self.stop_source(source_id)
            raise

    def _event(self, source_id):
        state = self.states[source_id]
        if self.scenario is None:
            return build_event(BY_ID[source_id].event_type)
        self._prepare()
        events = [e for e in self._plan if e['event_type'] == BY_ID[source_id].event_type]
        if state.cursor >= len(events):
            return None
        event = deepcopy(events[state.cursor]); state.cursor += 1
        return event

    def _send(self, source_id, *, manual=False):
        state = self.states[source_id]
        with state.io:
            with self.lock:
                self._check(source_id)
                if not manual and state.stop.is_set():
                    return False
                if manual and time.monotonic()-state.last_started < 1/state.rate:
                    raise RuntimeError('Rate máximo de la fuente; esperar antes del siguiente SEND ONCE')
                event = self._event(source_id)
                if event is None:
                    state.reason = 'Perfil completado'
                    return False
                state.produced += 1
                state.last_started = time.monotonic()
            record = dict(timestamp=datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
                source_application=BY_ID[source_id].name, source_id=source_id,
                event_type=event['event_type'], event_id=event['event_id'], message_id=None,
                event_timestamp=event['event_timestamp'], result='ERROR', event=event)
            try:
                validate_event(event)
                message = json.dumps(event,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':'))
                record['message_id'] = publish(self.config,self.resources,message,transport=self.transport)
                record['result'] = 'OK'
            except Exception:
                # No exponer excepciones del transporte: pueden contener credenciales o payload.
                record['error'] = 'Validación/publicación fallida; no se reintenta. Revisar acceso y conexión.'
            with self.lock:
                state.last_event_id, state.last_event_time = event['event_id'],event['event_timestamp']
                state.last_message_id = record['message_id'] or ''
                state.success += record['result']=='OK'
                state.errors += record['result']!='OK'
                state.samples.append(time.monotonic())
                self.activity.append(record)
                if record['result'] != 'OK':
                    state.reason = record['error'];state.stop.set()
            return record['result']=='OK'

    def send_once(self, source_id):
        with self.lock:
            self._check(source_id)
            if self.states[source_id].running:
                raise RuntimeError('Detener la fuente antes de SEND ONCE')
            if self.scenario and self._plan is None:
                self._prepare()
        return self._send(source_id,manual=True)

    def _worker(self, source_id):
        state = self.states[source_id]
        started = time.monotonic()
        try:
            while not state.stop.is_set():
                now = time.monotonic()
                with self.lock:
                    if now-self._heartbeat >= self.lease_seconds:
                        state.reason='Sesión desconectada';break
                    if now-started >= self.max_run_seconds:
                        state.reason='Ventana máxima completada';break
                    # Rate también protege reinicios y cambios durante ejecución.
                    due=state.last_started+1/state.rate
                if now >= due:
                    if not self._send(source_id):
                        break
                    continue  # Recalcula desde el envío real, sin catch-up ni cola.
                state.wake.wait(min(.1,max(0,due-time.monotonic())))
                state.wake.clear()
        except Exception:
            with self.lock:
                state.reason='Fuente detenida por seguridad'
        finally:
            with self.lock:
                state.running=False

    def stop_source(self, source_id):
        with self.lock:
            state=self.states[source_id]
            state.stop.set();state.wake.set();thread=state.thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=6)
            if thread.is_alive():
                raise RuntimeError('Envío aún en curso; no se iniciarán más mensajes')
        with self.lock:
            state.running=False

    def stop_all(self):
        with self.lock:
            for state in self.states.values():
                state.stop.set();state.wake.set()
        for source_id in self.states:
            self.stop_source(source_id)

    def close(self):
        with self.lock:
            self._closed=True
        self.stop_all()

    def snapshot(self):
        with self.lock:
            now=time.monotonic()
            rows={}
            for source_id,state in self.states.items():
                recent=[t for t in state.samples if now-t<=5]
                rows[source_id]=dict(rate=state.rate,status='RUNNING' if state.running else 'STOPPED',
                    produced=state.produced,events_sent=state.success,success=state.success,errors=state.errors,
                    observed_rate=len(recent)/5, last_event_id=state.last_event_id,
                    last_message_id=state.last_message_id,last_event_time=state.last_event_time,reason=state.reason)
            return dict(sources=rows,activity=deepcopy(list(reversed(self.activity))),
                total_produced=sum(s.produced for s in self.states.values()),
                successful_publishes=sum(s.success for s in self.states.values()),
                failed_publishes=sum(s.errors for s in self.states.values()),
                current_total_rate=sum(s.rate for s in self.states.values() if s.running),
                active_sources=sum(s.running for s in self.states.values()),
                elapsed_time=now-self._started if self._started else 0,
                closed=self._closed,scenario=self.scenario)
