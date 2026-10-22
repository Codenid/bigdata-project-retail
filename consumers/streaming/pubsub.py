"""REST unary pull/ACK: identidad operativa, sin IAM, retries ni auto-ACK."""
import json
import subprocess
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler

from producers.streaming.publish import check_operator

PERMISSION = 'pubsub.subscriptions.consume'


class TransportError(RuntimeError):
    """Error saneado: nunca expone tokens, ackIds ni respuestas del servidor."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Nunca reenviar Authorization a otro destino.


def target(config, resources):
    return f"projects/{config['GCP_PROJECT_ID']}/subscriptions/{resources['RS-STR-002']['name']}"


class Client:
    def __init__(self, config, resources):
        check_operator(config)
        self.subscription = target(config, resources)
        try:
            result = subprocess.run(['gcloud', 'auth', 'print-access-token',
                                     '--account=' + config['OPERATOR_ACCOUNT'],
                                     '--project=' + config['GCP_PROJECT_ID'], '--quiet'],
                                    capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            raise TransportError('No se pudo obtener credencial operativa; sin cambios de autenticación') from None
        self._token = result.stdout.strip()
        if result.returncode or not self._token or any(c.isspace() for c in self._token):
            raise TransportError('Credencial operativa no disponible')
        self._opener = build_opener(NoRedirect())

    def _post(self, action, body):
        request = Request('https://pubsub.googleapis.com/v1/' + self.subscription + ':' + action,
                          data=json.dumps(body).encode('utf-8'), method='POST',
                          headers={'Authorization': 'Bearer ' + self._token,
                                   'Content-Type': 'application/json'})
        try:
            with self._opener.open(request, timeout=60) as response:
                data = json.loads(response.read().decode('utf-8'))
        except HTTPError as error:
            if error.code == 403:
                raise TransportError('Acceso denegado: requiere pubsub.subscriptions.consume sobre RS-STR-002; IAM necesita aprobación separada') from None
            raise TransportError(f'Pub/Sub {action}: HTTP {error.code}; no se reintenta') from None
        except (URLError, OSError, ValueError):
            raise TransportError(f'Pub/Sub {action}: respuesta no confirmada; no se reintenta') from None
        if not isinstance(data, dict):
            raise TransportError(f'Pub/Sub {action}: respuesta inválida')
        return data

    def check_access(self):
        permissions = self._post('testIamPermissions', {'permissions': [PERMISSION]}).get('permissions', [])
        if PERMISSION not in permissions:
            raise TransportError('No se confirmó pubsub.subscriptions.consume sobre RS-STR-002; detener y revisar acceso/IAM sin modificarlo')
        # Es una comprobación informativa; la autorización definitiva la aplica pull.

    def pull(self, limit):
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError('limit debe estar entre 1 y 50')
        data = self._post('pull', {'maxMessages': limit})
        rows = data.get('receivedMessages', [])
        if not isinstance(rows, list) or len(rows) > limit:
            raise TransportError('Respuesta pull inválida; no se envía ACK')
        return rows

    def acknowledge(self, ack_ids):
        if not ack_ids or any(not isinstance(a, str) or not a for a in ack_ids):
            raise ValueError('Lote ACK inválido')
        if self._post('acknowledge', {'ackIds': ack_ids}) != {}:
            raise TransportError('ACK no confirmado: respuesta inesperada')
