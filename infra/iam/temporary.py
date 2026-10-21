"""Binding de aprovisionamiento temporal, preservando accesos preexistentes."""
from contextlib import contextmanager
from infra.iam.manage import has_binding


@contextmanager
def temporary_role(config, manifest, stats, run, service):
    email = config['DEPLOYER_SERVICE_ACCOUNT_ID'] + '@' + config['GCP_PROJECT_ID'] + '.iam.gserviceaccount.com'
    member = 'serviceAccount:' + email
    policy = run(config, 'projects', 'get-iam-policy', config['GCP_PROJECT_ID'])
    present = has_binding(policy, manifest['deployer_role'], member)
    created = not present
    stats['preexisting_binding'] = present
    failure = None
    try:
        if created:
            # Registrar intención antes de invocar; si el comando falla tras aplicar,
            # finally consulta y retira solo el binding ausente en el estado inicial.
            run(config, 'projects', 'add-iam-policy-binding', config['GCP_PROJECT_ID'],
                '--member=' + member, '--role=' + manifest['deployer_role'], '--condition=None')
            stats['iam_changes'] += 1
            print(f'[OK] Binding {service} temporal asignado por bootstrap', flush=True)
        else:
            print(f"[INFO] {service}: binding preexistente {manifest['deployer_role']}; se conserva sin cambios", flush=True)
        yield '--impersonate-service-account=' + email
    except BaseException as error:
        failure = error
        raise
    finally:
        if created:
            try:
                policy = run(config, 'projects', 'get-iam-policy', config['GCP_PROJECT_ID'])
                if has_binding(policy, manifest['deployer_role'], member):
                    run(config, 'projects', 'remove-iam-policy-binding', config['GCP_PROJECT_ID'],
                        '--member=' + member, '--role=' + manifest['deployer_role'], '--condition=None')
                    stats['iam_changes'] += 1
                policy = run(config, 'projects', 'get-iam-policy', config['GCP_PROJECT_ID'])
                if has_binding(policy, manifest['deployer_role'], member):
                    raise RuntimeError('Binding temporal aún presente')
                stats['temporary_binding_removed'] = True
                print('[OK] Binding temporal retirado y política confirmada', flush=True)
            except Exception as cleanup_error:
                message = 'ERROR DE LIMPIEZA IAM: ' + str(cleanup_error)
                if failure:
                    message += '; operación original: ' + str(failure)
                raise RuntimeError(message) from cleanup_error
