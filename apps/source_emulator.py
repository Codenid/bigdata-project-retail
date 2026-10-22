"""RetailSmart Source Emulator — interfaz local, engine independiente."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

import streamlit as st
from infra.config.settings import load
from producers.emulator.engine import ProducerEngine
from producers.emulator.sources import SOURCES, compatible
from producers.emulator.transport import OperatorPublisher
from producers.streaming.publish import target
from producers.streaming.scenarios import definitions

st.set_page_config(page_title='RetailSmart · Source Emulator',page_icon='◈',layout='wide')
st.markdown('''<style>
.block-container {padding-top:2rem;max-width:1500px}
h1 {letter-spacing:-.045em;font-weight:750!important}
h3 {letter-spacing:-.02em}
[data-testid="stMetricValue"] {font-size:1.8rem}
[data-testid="stMetricLabel"] {color:#92a7c6}
[data-testid="stVerticalBlockBorderWrapper"] {border-radius:16px}
[data-testid="stSidebar"] {border-right:1px solid #22344e}
.brand {color:#5de0ae;font-size:.75rem;letter-spacing:.2em;font-weight:700}
.hero {color:#98abc5;font-size:1rem;max-width:700px;margin-bottom:1.5rem}
</style>''',unsafe_allow_html=True)

if 'engine' not in st.session_state:
    st.session_state.engine=None

with st.sidebar:
    st.markdown('## ◈ RetailSmart')
    st.caption('SOURCE EMULATOR / V1')
    page=st.radio('Workspace',['Overview','Streaming','Batch','Activity'],label_visibility='collapsed')
    st.divider()
    try:
        config,resources=load(ROOT/'config/dev.env')
        st.caption('DESTINO STREAMING')
        st.code(resources['RS-STR-001']['name'],language=None)
        st.caption(config['ENVIRONMENT'].upper()+' · '+config['GCP_REGION'])
    except (OSError,ValueError,KeyError):
        st.error('Completa config/dev.env con la configuración oficial.')
        st.stop()
    engine=st.session_state.engine
    if engine is None or engine.snapshot()['closed']:
        if st.button('Conectar OPERATOR_ACCOUNT',key='connect_operator',type='primary',width='stretch'):
            try:
                with st.spinner('Verificando identidad operativa…'):
                    transport=OperatorPublisher(config,resources)
                    st.session_state.engine=ProducerEngine(config,resources,transport)
                st.rerun()
            except Exception:
                st.error('No se pudo conectar. Revisa OPERATOR_ACCOUNT y la autenticación activa de gcloud. No se modificó IAM.')
    else:
        st.success('Identidad operativa verificada')
        if st.button('Desconectar y detener',key='disconnect_operator',width='stretch'):
            engine.close()
            st.session_state.engine=None
            st.rerun()
    st.divider()
    st.caption('Solo fuentes sintéticas. Sin consumo, ACK ni cambios de infraestructura.')

st.markdown('<div class="brand">RETAILSMART / SOURCE OPERATIONS</div>',unsafe_allow_html=True)
st.title({'Overview':'Tus fuentes, en movimiento.','Streaming':'Fuentes streaming','Batch':'Batch sources','Activity':'Live activity'}[page])
st.markdown('<div class="hero">Emula aplicaciones y dispositivos de origen. Observa cada hecho validado y su confirmación de publicación en Pub/Sub.</div>',unsafe_allow_html=True)


def action(function,*args):
    try:
        function(*args)
    except (ValueError,RuntimeError):
        st.error('Acción no disponible: revisa compatibilidad, rate, sesión activa y envíos en curso.')


def activity_view(activity):
    if not activity:
        st.info('Todavía no hay eventos. Conecta la identidad y usa START o SEND ONCE en una fuente.')
        return
    st.dataframe([{k:v for k,v in row.items() if k in (
        'timestamp','source_application','event_type','event_id','message_id','result')}
        for row in activity],hide_index=True,width='stretch')
    selected=st.selectbox('Inspeccionar evento JSON',range(len(activity)),
        format_func=lambda index:activity[index]['source_application']+' · '+activity[index]['event_id'],key='inspect_event')
    st.json(activity[selected]['event'],expanded=False)
    if activity[selected]['result']!='OK':
        st.error(activity[selected].get('error','Publicación no confirmada'))


@st.fragment(run_every=.5)
def workspace():
    engine=st.session_state.engine
    connected=engine is not None and not engine.snapshot()['closed']
    if connected:
        engine.heartbeat()
        snapshot=engine.snapshot()
    else:
        snapshot=dict(total_produced=0,successful_publishes=0,failed_publishes=0,
            current_total_rate=0,active_sources=0,elapsed_time=0,activity=[])
    metrics=st.columns(6)
    for column,label,value in zip(metrics,['Total produced','Successful publishes','Failed publishes','Current total rate','Active sources','Elapsed time'],
        [snapshot['total_produced'],snapshot['successful_publishes'],snapshot['failed_publishes'],
         f"{snapshot['current_total_rate']:g} evt/s",snapshot['active_sources'],f"{snapshot['elapsed_time']:.0f}s"]):
        column.metric(label,value)
    st.divider()
    if page=='Batch':
        with st.container(border=True):
            st.markdown('### Batch sources')
            st.info('Coming next')
            st.caption('La navegación está preparada. V1 emula únicamente fuentes streaming.')
        return
    if page=='Activity':
        st.caption('Últimos 50 eventos de esta sesión. OK confirma publicación, no procesamiento downstream.')
        activity_view(snapshot['activity'])
        return
    if not connected:
        st.info('Conecta OPERATOR_ACCOUNT para habilitar la publicación real. Abrir esta página no genera eventos.')
    left,right=st.columns([3,1])
    labels=['Operación libre']+list(definitions()['profiles'])
    selected=left.selectbox('Escenario compartido',labels,disabled=not connected or snapshot['active_sources']>0,key='scenario')
    scenario=None if selected=='Operación libre' else selected
    if connected and engine.scenario!=scenario:
        action(engine.set_scenario,scenario)
    if scenario:
        st.caption('Perfil finito · reloj de eventos simulado según el perfil original. Rate controla emisión; el escenario no se incluye en el evento.')
    else:
        st.caption('Operación libre · hechos sintéticos independientes con UUID nuevos. STOP antes de cambiar escenario.')
    with right:
        a,b=st.columns(2)
        if a.button('START ALL',key='start_all',disabled=not connected,width='stretch') and connected:
            action(engine.start_all)
        if b.button('STOP ALL',key='stop_all',disabled=not connected,width='stretch') and connected:
            action(engine.stop_all)
    columns=st.columns(2)
    for index,source in enumerate(SOURCES):
        enabled=connected and compatible(source.id,scenario)
        state=engine.snapshot()['sources'][source.id] if connected else dict(status='STOPPED',rate=1,
            events_sent=0,success=0,errors=0,observed_rate=0,last_event_id='',last_message_id='',last_event_time='',reason='')
        with columns[index%2],st.container(border=True):
            title,status=st.columns([4,1])
            title.markdown('### '+source.icon+' '+source.name)
            status.markdown('🟢 RUNNING' if state['status']=='RUNNING' else '⚪ STOPPED')
            st.caption(source.description+' · '+source.event_type)
            if not compatible(source.id,scenario):
                st.caption('Esta fuente no participa en el escenario seleccionado.')
            r1,r2=st.columns([1,2])
            preset=r1.selectbox('Rate', [r for r in ['1','2','5','10'] if float(r)<=(engine.max_rate if connected else 20)]+['Custom'],key='preset_'+source.id,disabled=not enabled)
            rate=float(preset) if preset!='Custom' else r2.number_input('Eventos / segundo',min_value=.1,max_value=float(engine.max_rate if connected else 20),value=min(1.0,float(engine.max_rate if connected else 20)),step=.1,key='custom_'+source.id,disabled=not enabled)
            if connected and enabled and rate!=state['rate']:
                action(engine.set_rate,source.id,rate)
            r2.caption(f"Objetivo {state['rate']:g} evt/s · observado {state['observed_rate']:.1f} evt/s (5s)")
            start,stop,once=st.columns(3)
            if start.button('START',key='start_'+source.id,type='primary',disabled=not enabled or state['status']=='RUNNING',width='stretch') and enabled:
                action(engine.start_source,source.id)
            if stop.button('STOP',key='stop_'+source.id,disabled=not connected or state['status']!='RUNNING',width='stretch') and connected:
                action(engine.stop_source,source.id)
            if once.button('SEND ONCE',key='once_'+source.id,disabled=not enabled or state['status']=='RUNNING',width='stretch') and enabled:
                action(engine.send_once,source.id)
            m1,m2,m3=st.columns(3)
            m1.metric('Events sent',state['events_sent']);m2.metric('Success',state['success']);m3.metric('Errors',state['errors'])
            with st.expander('Última publicación',expanded=False):
                st.text('Event ID: '+(state['last_event_id'] or '—'))
                st.text('Message ID: '+(state['last_message_id'] or '—'))
                st.text('Event time: '+(state['last_event_time'] or '—'))
            if state['reason']:
                st.caption(state['reason'])
    if page=='Overview':
        st.markdown('### Actividad reciente')
        activity_view(snapshot['activity'])
    thermal=[row for row in reversed(snapshot['activity']) if row['event_type']=='telemetry_event']
    if thermal:
        st.markdown('### Cámaras frigoríficas · temperatura observada')
        st.line_chart([row['event']['payload']['value'] for row in thermal],y_label='°C',x_label='Muestra sintética')
    st.caption('STOP detiene nuevos envíos y espera el que esté en curso. Cerrar la pestaña detiene las fuentes al vencer el lease (máx. 10s + envío en curso). Ventana máxima: 300s por START.')

workspace()
