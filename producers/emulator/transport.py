"""Transporte REST de publicación unitaria, sin retries ni configuración IAM."""
import base64
import json
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler

from producers.streaming.publish import check_operator, target


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class OperatorPublisher:
    def __init__(self, config, resources, timeout=5):
        check_operator(config)
        try:
            result = subprocess.run(['gcloud','auth','print-access-token',
                '--account='+config['OPERATOR_ACCOUNT'], '--project='+config['GCP_PROJECT_ID'], '--quiet'],
                capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            raise RuntimeError('No se pudo verificar la sesión operativa') from None
        self._token = result.stdout.strip()
        if result.returncode or not self._token or any(c.isspace() for c in self._token):
            raise RuntimeError('Credencial operativa no disponible')
        self._target = target(config, resources)
        self._operator = config['OPERATOR_ACCOUNT']
        self._expires = time.monotonic()+2400
        self.timeout = timeout

    def __call__(self, config, resources, message):
        if target(config, resources) != self._target or config['OPERATOR_ACCOUNT'] != self._operator:
            raise RuntimeError('El destino o identidad cambió; reconectar')
        if time.monotonic() >= self._expires:
            raise RuntimeError('Sesión operativa vencida; reconectar antes de publicar')
        body = {'messages':[{'data':base64.b64encode(message.encode('utf-8')).decode('ascii')}]}
        request = Request('https://pubsub.googleapis.com/v1/'+self._target+':publish',
            data=json.dumps(body).encode(), method='POST',
            headers={'Authorization':'Bearer '+self._token, 'Content-Type':'application/json'})
        try:
            # Un opener por llamada evita compartir conexiones mutables entre fuentes.
            with build_opener(NoRedirect()).open(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode('utf-8'))
        except HTTPError as error:
            if error.code == 403:
                raise PermissionError('Se requiere pubsub.topics.publish sobre RS-STR-001; no se modifica IAM') from None
            raise RuntimeError('Publicación REST rechazada; sin reintentos') from None
        except (OSError, URLError, ValueError):
            raise RuntimeError('Publicación no confirmada; no reenviar automáticamente') from None
