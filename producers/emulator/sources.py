"""Catálogo local de fuentes de la Arquitectura de Solución, extensible a Batch."""
from dataclasses import dataclass
from producers.streaming.scenarios import definitions


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    event_type: str
    icon: str
    description: str
    kind: str = 'streaming'


SOURCES = (
    Source('channel', 'Aplicaciones de Canal Web/App/POS', 'clic_event', '↗', 'Interacciones de clientes en los canales digitales.'),
    Source('iot', 'Sensores IoT de Tienda', 'iot_event', '◉', 'Ocupación y observaciones del espacio comercial.'),
    Source('shelf', 'Estantería Inteligente', 'stock_event', '▤', 'Disponibilidad observada de productos en estantería.'),
    Source('logistics', 'Tracking Logístico / Repartidores', 'location_event', '⌁', 'Posición, movimiento y compromiso de entregas.'),
    Source('cold_room', 'Cámaras Frigoríficas', 'telemetry_event', '❄', 'Temperatura de almacenamiento refrigerado.'),
    Source('warehouse', 'Sensores de Almacén', 'warehouse_sensor_event', '◇', 'Vibración y estado de equipos de almacén.'),
)
BY_ID = {s.id:s for s in SOURCES}


def compatible(source_id, scenario):
    source = BY_ID[source_id]
    return scenario is None or any(row['event_type'] == source.event_type
                                   for row in definitions()['profiles'][scenario]['steps'])
