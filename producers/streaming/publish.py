"""Adaptador gcloud operativo, independiente del builder y sin cambios IAM."""
import json
import os
import shutil
import subprocess
import sys


class PublicationError(RuntimeError):
    def __init__(self, message, uncertain=False):
        super().__init__(message)
        self.uncertain = uncertain


def target(config, resources):
    return f"projects/{config['GCP_PROJECT_ID']}/topics/{resources['RS-STR-001']['name']}"


def _run(config, *args, select_operator=False):
    if not shutil.which('gcloud'):
        raise RuntimeError('gcloud no está instalado o no está en PATH')
    command = ['gcloud', *args, '--project=' + config['GCP_PROJECT_ID'], '--quiet', '--format=json']
    if select_operator:
        command.append('--account=' + config['OPERATOR_ACCOUNT'])
    session = os.environ.copy()
    try:
        result = subprocess.run(command, text=True, capture_output=True, timeout=180, env=session)
    except subprocess.TimeoutExpired as error:
        if error.stderr:
            stderr = error.stderr.decode(errors='replace') if isinstance(error.stderr, bytes) else error.stderr
            print(stderr, file=sys.stderr, end='')
        raise
    if result.stderr:
        print(result.stderr, file=sys.stderr, end='')
    if result.returncode:
        if 'PERMISSION_DENIED' in result.stderr or '403' in result.stderr:
            raise PermissionError('Acceso denegado: se requiere pubsub.topics.publish sobre RS-STR-001; '
                               'cualquier asignación de roles necesita aprobación separada')
        raise RuntimeError(f'gcloud {args[0]} falló (código {result.returncode}); ver stderr')
    return json.loads(result.stdout or 'null')


def check_operator(config):
    operator = config.get('OPERATOR_ACCOUNT', '').strip()
    if not operator or any(character.isspace() for character in operator):
        raise ValueError('Falta configurar OPERATOR_ACCOUNT válido; no se deriva de BOOTSTRAP_ACCOUNT')
    # Sin --account: seleccionar la cuenta aquí ocultaría un mismatch de cuenta activa.
    accounts = _run(config, 'auth', 'list', '--filter=status:ACTIVE')
    if not isinstance(accounts, list) or len(accounts) != 1 or not isinstance(accounts[0], dict) or accounts[0].get('account') != operator:
        raise RuntimeError('La cuenta activa de gcloud no corresponde a OPERATOR_ACCOUNT; no se modifica autenticación')
    settings = _run(config, 'config', 'list', 'auth/')
    if not isinstance(settings, dict) or not isinstance(settings.get('auth', {}), dict):
        raise RuntimeError('No se pudo verificar la configuración de autenticación; no se publica')
    auth = settings.get('auth', {})
    overrides = ('impersonate_service_account', 'credential_file_override', 'access_token_file', 'access_token')
    if any(auth.get(key) for key in overrides) or any(
            os.environ.get('CLOUDSDK_AUTH_' + key.upper()) for key in overrides):
        raise RuntimeError('Override de credenciales/impersonación incompatible con OPERATOR_ACCOUNT; no se publica')


def publish(config, resources, message, *, transport=None):
    """Una invocación publish; no reintenta desde la aplicación ni usa IAM admin."""
    try:
        response = (transport(config, resources, message) if transport is not None else
                    _run(config, 'pubsub', 'topics', 'publish', target(config, resources),
                         '--message=' + message, select_operator=True))
    except subprocess.TimeoutExpired as error:
        raise PublicationError('Timeout: publicación no confirmada; puede haberse aceptado el mensaje. No reintentar automáticamente', True) from error
    except PermissionError as error:
        raise PublicationError(str(error)) from error
    except (OSError, RuntimeError, ValueError) as error:
        raise PublicationError(str(error), True) from error
    ids = response.get('messageIds') if isinstance(response, dict) else None
    if not isinstance(ids, list) or len(ids) != 1 or not isinstance(ids[0], str) or not ids[0].strip():
        raise PublicationError('Respuesta sin un message_id válido: publicación no confirmada; no reintentar automáticamente', True)
    return ids[0]
