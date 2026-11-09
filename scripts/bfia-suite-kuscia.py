#!/usr/bin/env python3
"""Install and run the fixed eight-algorithm image as a Kuscia job."""
import argparse
import base64
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import subprocess
import sys
import tarfile
import tempfile
import time

UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
DIGEST = re.compile(r'sha256:[0-9a-f]{64}')
NAME = re.compile(r'[a-z0-9](?:[a-z0-9.-]{0,61}[a-z0-9])?')
LABEL, COMPONENT, APP_IMAGE = 'io.ppci/component', 'bfia-suite', 'ppci-bfia-suite'
PYTHON = ('sgb', 'he_woe')
CPP = ('ecdh-psi', 'ss-lr', 'ss-xgb', 'ss-pearson', 'ss-vif', 'ss-compare')
MAX_BUNDLE, MAX_EXPANDED, MAX_LOG_RESPONSE = 8 * 1024 * 1024, 64 * 1024 * 1024, 32 * 1024 * 1024


def command(*args, data=None, check=True, timeout=30):
    result = subprocess.run(list(map(str, args)), input=data, capture_output=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError('Command failed: ' + ' '.join(map(str, args[:5])) + '\n' + result.stderr.decode(errors='replace')[-2000:])
    return result


def kubectl(config, *args, data=None, check=True, timeout=30):
    return command('docker', 'exec', '-i', config['container'], 'kubectl', *args,
                   data=data, check=check, timeout=timeout)


def object_json(config, *args, check=True):
    result = kubectl(config, *args, '-o', 'json', check=check)
    if result.returncode:
        return None
    if len(result.stdout) > 2 * 1024 * 1024:
        raise RuntimeError('Kuscia metadata exceeds its read limit')
    return json.loads(result.stdout)


def private_write(path, data):
    parent = path.parent
    while parent != parent.parent:
        if parent.is_symlink():
            raise RuntimeError('Refuse a symbolic-link output directory')
        parent = parent.parent
    if path.is_symlink():
        raise RuntimeError('Refuse a symbolic-link output file')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.suite-', delete=False) as output:
        temporary = Path(output.name)
        try:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def config_values(image_ref, image_tag, image_id, container='gaofeng-kuscia-autonomy-alice', domain='alice'):
    repository, separator, digest = image_ref.partition('@')
    if not separator or not DIGEST.fullmatch(digest) or not re.fullmatch(r'[a-z0-9][a-z0-9./:_-]*', repository):
        raise ValueError('The suite image must be pinned by its registry sha256 digest')
    if not image_tag.startswith(repository + ':') or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}', image_tag[len(repository) + 1:]):
        raise ValueError('The suite image tag must name the same repository and a fixed release')
    if image_tag.rsplit(':', 1)[1] == 'latest' or not DIGEST.fullmatch(image_id):
        raise ValueError('A fixed tag and Docker image ID are required')
    if not NAME.fullmatch(container) or not NAME.fullmatch(domain):
        raise ValueError('Invalid Kuscia container or domain')
    return {'image_ref': image_ref, 'image_tag': image_tag, 'image_id': image_id,
            'container': container, 'domain': domain, 'app_image': APP_IMAGE, 'timeout_seconds': 900}


def app_image(config):
    repository, tag = config['image_tag'].rsplit(':', 1)
    return {'apiVersion': 'kuscia.secretflow/v1alpha1', 'kind': 'AppImage',
            'metadata': {'name': APP_IMAGE, 'labels': {LABEL: COMPONENT}},
            'spec': {'image': {'name': repository, 'tag': tag, 'id': config['image_id']},
                     'deployTemplates': [{'name': 'suite', 'role': 'runner', 'replicas': 1,
                       'spec': {'restartPolicy': 'Never', 'containers': [{
                           'name': 'suite', 'workingDir': '/',
                           'command': ['/usr/local/bin/bfia-suite'], 'args': ['--kuscia'],
                           'env': [{'name': 'BFIA_RUN_ID', 'valueFrom': {'fieldRef': {
                               'fieldPath': "metadata.annotations['kuscia.secretflow/task-id']"}}}],
                           'resources': {'requests': {'cpu': '2', 'memory': '4Gi'},
                                         'limits': {'cpu': '4', 'memory': '6Gi'}}}]}}]}}


def job(config, run_id):
    if not UUID.fullmatch(run_id):
        raise ValueError('Invalid suite run ID')
    return {'apiVersion': 'kuscia.secretflow/v1alpha1', 'kind': 'KusciaJob',
            'metadata': {'name': 'ppci-suite-' + run_id, 'namespace': 'cross-domain',
                         'labels': {LABEL: COMPONENT, 'io.ppci/run-id': run_id}},
            'spec': {'initiator': config['domain'], 'maxParallelism': 1,
                     'tasks': [{'alias': 'suite', 'taskID': run_id, 'appImage': APP_IMAGE,
                                'parties': [{'domainID': config['domain'], 'role': 'runner'}],
                                'taskInputConfig': '{}', 'tolerable': False}]}}


def read_config(runtime):
    path = runtime / 'etc/bfia-suite.json'
    info = path.lstat()
    if path.is_symlink() or info.st_mode & 0o022 or info.st_uid not in (0, os.geteuid()):
        raise RuntimeError('The fixed suite configuration is not protected')
    config = json.loads(path.read_text())
    return config_values(config['image_ref'], config['image_tag'], config['image_id'],
                         config['container'], config['domain'])


def safe_relative(name, run_id, live=False):
    path = PurePosixPath(name)
    if not name or len(name) > 1024 or any(ord(c) < 32 for c in name) or str(path) != name or path.is_absolute() or '..' in path.parts or '.' in path.parts:
        raise ValueError('Unsafe suite artifact path')
    if not live and name in ('report.json', 'exit-code'):
        return path
    if len(path.parts) < 3 or path.parts[0] not in ('python', 'cpp') or path.parts[1] != run_id:
        raise ValueError('Suite artifact belongs to another run')
    if live:
        logs = {f'{language}/{run_id}/{algorithm}/{party}{suffix}'
                for language, algorithms, suffix in (('python', PYTHON, '.stdout.log'), ('cpp', CPP, '.log'))
                for algorithm in algorithms for party in ('alice', 'bob')}
        reports = {f'{language}/{run_id}/{kind}-validation.json'
                   for language in ('python', 'cpp') for kind in ('numerical', 'protocol')}
        if name not in logs | reports:
            raise ValueError('Unexpected live suite artifact')
    return path


def unpack_bundle(payload, destination, run_id):
    if len(payload) > MAX_BUNDLE:
        raise ValueError('Suite bundle is too large')
    seen, total, exit_code = set(), 0, None
    with tarfile.open(fileobj=io.BytesIO(payload), mode='r|gz') as archive:
        for count, member in enumerate(archive, 1):
            if count > 1024 or member.name in seen or not (member.isdir() or member.isfile()):
                raise ValueError('Invalid suite bundle member')
            name = member.name.rstrip('/') if member.isdir() else member.name
            if member.isdir() and name in ('python', 'cpp', 'python/' + run_id, 'cpp/' + run_id):
                seen.add(member.name)
                continue
            relative = safe_relative(name, run_id)
            seen.add(member.name)
            if member.isdir():
                continue
            total += member.size
            if total > MAX_EXPANDED:
                raise ValueError('Expanded suite bundle is too large')
            content = archive.extractfile(member).read(member.size + 1)
            if len(content) != member.size:
                raise ValueError('Truncated suite artifact')
            if name == 'exit-code':
                code = content.decode('ascii').strip()
                if not re.fullmatch(r'0|[1-9][0-9]{0,2}', code) or int(code) > 255:
                    raise ValueError('Invalid task exit code')
                exit_code = int(code)
            else:
                private_write(destination / str(relative), content)
    if exit_code is None:
        raise ValueError('Suite bundle has no exit code')
    return exit_code


def frames(logs, run_id):
    """Read complete SHA-checked frames; polling may stop inside the next frame."""
    active = None
    for line in logs.splitlines():
        parts = line.split()
        if not parts or not parts[0].startswith('PPCI_BFIA_'):
            continue
        marker = parts[0]
        if marker in ('PPCI_BFIA_BUNDLE_BEGIN', 'PPCI_BFIA_FILE_BEGIN'):
            is_file = marker == 'PPCI_BFIA_FILE_BEGIN'
            if len(parts) != (5 if is_file else 4) or parts[1] != run_id:
                raise ValueError('Invalid suite artifact frame')
            name = parts[2] if is_file else None
            sha, size = parts[-2:]
            maximum = 256 * 1024 if is_file else MAX_BUNDLE
            if not re.fullmatch(r'[0-9a-f]{64}', sha) or not size.isdigit() or int(size) > maximum:
                raise ValueError('Invalid suite frame checksum or size')
            if is_file:
                safe_relative(name, run_id, live=True)
            active = {'kind': 'FILE' if is_file else 'BUNDLE', 'name': name,
                      'sha': sha, 'size': int(size), 'chunks': [], 'encoded': 0}
        elif active and marker == 'PPCI_BFIA_' + active['kind'] + '_DATA':
            if len(parts) != 2 or len(parts[1]) > 4096:
                raise ValueError('Invalid suite frame chunk')
            active['encoded'] += len(parts[1])
            if active['encoded'] > ((active['size'] + 2) // 3) * 4:
                raise ValueError('Suite frame exceeds its declared size')
            active['chunks'].append(parts[1])
        elif active and marker == 'PPCI_BFIA_' + active['kind'] + '_END':
            if parts != [marker, run_id] + ([active['name']] if active['name'] else []):
                raise ValueError('Suite frame terminator does not match')
            payload = base64.b64decode(''.join(active['chunks']), validate=True)
            if len(payload) != active['size'] or hashlib.sha256(payload).hexdigest() != active['sha']:
                raise ValueError('Suite artifact checksum mismatch')
            yield active['kind'], active['name'], payload
            active = None


def verified_reports(destination, run_id):
    for language, algorithms, suffix in (('python', PYTHON, '.stdout.log'), ('cpp', CPP, '.log')):
        base = destination / language / run_id
        numerical = json.loads((base / 'numerical-validation.json').read_text())
        protocol = json.loads((base / 'protocol-validation.json').read_text())
        if set(numerical) != set(algorithms) or set(protocol) != set(algorithms):
            return False
        for algorithm in algorithms:
            if numerical[algorithm].get('pass') is not True or protocol[algorithm].get('pass') is not True:
                return False
            for party in ('alice', 'bob'):
                content = (base / algorithm / (party + suffix)).read_bytes()
                if hashlib.sha256(content).hexdigest() != protocol[algorithm].get('log_sha256', {}).get(party + suffix):
                    return False
    return True


def cri_logs(raw):
    """Strip CRI envelopes, retaining complete records and joining partial lines."""
    output, partial = [], b''
    for line in raw.splitlines(keepends=True):
        if not line.endswith(b'\n'):
            break  # The running container may still be writing its last record.
        parts = line[:-1].split(b' ', 3)
        if len(parts) != 4 or parts[1] not in (b'stdout', b'stderr') or parts[2] not in (b'P', b'F'):
            raise ValueError('Invalid node-local CRI log record')
        partial += parts[3]
        if len(partial) > 256 * 1024:
            raise ValueError('Node-local CRI log line exceeds its read limit')
        if parts[2] == b'F':
            output.append(partial + b'\n')
            partial = b''
    return b''.join(output)


def pod_logs(config, pod, run_id):
    metadata = pod['metadata']
    if (metadata.get('namespace') != config['domain'] or metadata.get('name') != run_id + '-runner-0'
            or not UUID.fullmatch(metadata.get('uid', ''))
            or metadata.get('annotations', {}).get('kuscia.secretflow/task-id') != run_id
            or metadata.get('annotations', {}).get('kuscia.secretflow/image-id') != config['image_id']):
        raise RuntimeError('Kuscia did not select the owned pod and pinned suite image')
    for status in pod.get('status', {}).get('containerStatuses', []):
        if status.get('name') == 'suite' and (status.get('restartCount', 0) != 0
                or status.get('imageID', config['image_id']) != config['image_id']):
            raise RuntimeError('The suite container image or restart identity changed')
    logs = kubectl(config, 'logs', '-n', config['domain'], metadata['name'], '-c', 'suite',
                   '--limit-bytes=' + str(MAX_LOG_RESPONSE), check=False)
    transport = 'kubectl'
    if logs.returncode:
        # Kuscia CRIProvider uses this directory even when no kubelet log endpoint is exposed.
        path = '/home/kuscia/var/stdout/pods/' + config['domain'] + '_' + metadata['name'] + '_' + metadata['uid'] + '/suite/0.log'
        logs = command('docker', 'exec', config['container'], 'head', '-c', str(MAX_LOG_RESPONSE + 1), path, check=False)
        transport = 'node-local-cri'
    if logs.returncode:
        return None
    if len(logs.stdout) > MAX_LOG_RESPONSE:
        raise RuntimeError('Suite logs exceeded their read limit')
    return (cri_logs(logs.stdout) if transport == 'node-local-cri' else logs.stdout), transport


def import_image(config):
    with tempfile.TemporaryFile() as errors:
        producer = subprocess.Popen(['docker', 'image', 'save', config['image_tag']], stdout=subprocess.PIPE, stderr=errors)
        try:
            loaded = subprocess.run(['docker', 'exec', '-i', config['container'], 'kuscia', 'image', 'load'],
                                    stdin=producer.stdout, capture_output=True, timeout=600)
            producer.stdout.close()
            code = producer.wait(timeout=30)
            if loaded.returncode or code:
                raise RuntimeError('Cannot import pinned suite image into Kuscia: ' + loaded.stderr.decode(errors='replace')[-2000:])
        finally:
            if producer.poll() is None:
                producer.kill()
                producer.wait()


def install_locked(args):
    runtime = args.runtime_root.resolve()
    config = config_values(args.image_ref, args.image_tag, args.image_id, args.container, args.domain)
    inspected = json.loads(command('docker', 'image', 'inspect', config['image_tag']).stdout)[0]
    if inspected['Id'] != config['image_id'] or inspected['Architecture'] != 'amd64':
        raise RuntimeError('The pulled suite image does not match the release or architecture')
    # Offline docker save/load retains tags and content IDs, but may omit RepoDigests.
    by_digest = command('docker', 'image', 'inspect', config['image_ref'], check=False)
    if by_digest.returncode == 0 and json.loads(by_digest.stdout)[0]['Id'] != config['image_id']:
        raise RuntimeError('The suite registry digest resolves to another image')
    previous = object_json(config, 'get', 'appimage', APP_IMAGE, check=False)
    if previous and previous.get('metadata', {}).get('labels', {}).get(LABEL) != COMPONENT:
        raise RuntimeError('Refuse to replace an unrelated Kuscia AppImage')
    import_image(config)
    kubectl(config, 'apply', '-f', '-', data=json.dumps(app_image(config)).encode())
    private_write(runtime / 'etc/bfia-suite.json', (json.dumps(config, indent=2) + '\n').encode())
    script = runtime / 'NewProject/scripts/environments/bfia-suite-kuscia.py'
    private_write(script, Path(__file__).read_bytes())
    script.chmod(0o755)
    source = Path(__file__).resolve().parents[1] / 'platform/scripts/linux-migration/run-bfia-suite.sh'
    if source.is_file():
        wrapper = runtime / 'NewProject/scripts/linux-migration/run-bfia-suite.sh'
        private_write(wrapper, source.read_bytes())
        wrapper.chmod(0o755)
    print('Registered pinned BFIA suite AppImage: ' + config['image_ref'])


def install(args):
    root = Path(os.environ.get('PPCI_BFIA_SUITE_ROOT', '/var/log/ppci/bfia-suite'))
    if not root.is_absolute() or root == Path('/') or root.is_symlink():
        raise ValueError('Invalid suite result root')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / 'runner.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        config = config_values(args.image_ref, args.image_tag, args.image_id, args.container, args.domain)
        existing = object_json(config, 'get', 'kusciajobs', '-n', 'cross-domain', '-l', LABEL + '=' + COMPONENT)
        if any(item.get('status', {}).get('phase') not in ('Succeeded', 'Failed', 'Cancelled', 'ApprovalReject')
               for item in existing.get('items', [])):
            raise RuntimeError('A suite job is active; retain its image until it finishes')
        install_locked(args)


def cancel_own_job(config, name, uid):
    current = object_json(config, 'get', 'kusciajob', '-n', 'cross-domain', name, check=False)
    if current and current.get('metadata', {}).get('uid') == uid and current['metadata'].get('labels', {}).get(LABEL) == COMPONENT:
        kubectl(config, 'delete', 'kusciajob', '-n', 'cross-domain', name,
                '--wait=true', '--timeout=30s', check=False, timeout=35)


def execute(args):
    run_id = args.run_id
    if not UUID.fullmatch(run_id):
        raise ValueError('Invalid suite run ID')
    root = Path(os.environ.get('PPCI_BFIA_SUITE_ROOT', ''))
    destination = root / 'runs' / run_id
    if not root.is_absolute() or root == Path('/') or not root.is_dir() or root.is_symlink() or not destination.is_dir() or destination.is_symlink():
        raise ValueError('Missing private suite run directory')
    root = root.resolve()
    destination = root / 'runs' / run_id
    if (root / 'runs').is_symlink() or root.stat().st_mode & 0o022:
        raise ValueError('The suite result directory is not protected')
    if any((destination / name).exists() for name in ('python', 'cpp', 'exit-code')):
        raise ValueError('Refuse to reuse a suite run')
    destination.chmod(0o700)
    config = read_config(args.runtime_root.resolve())
    name, uid, completed, result_code = 'ppci-suite-' + run_id, None, False, 1
    with (root / 'runner.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            existing = object_json(config, 'get', 'kusciajobs', '-n', 'cross-domain', '-l', LABEL + '=' + COMPONENT)
            terminal = {'Succeeded', 'Failed', 'Cancelled', 'ApprovalReject'}
            if any(item.get('status', {}).get('phase') not in terminal for item in existing.get('items', [])):
                raise RuntimeError('Another suite Kuscia job is active')
            created = json.loads(kubectl(config, 'create', '-f', '-', '-o', 'json', data=json.dumps(job(config, run_id)).encode()).stdout)
            uid = created['metadata']['uid']
            private_write(destination / 'execution.json', (json.dumps(dict(config, job=name, job_uid=uid), indent=2) + '\n').encode())
            print('Kuscia job=' + name + ' image=' + config['image_ref'], flush=True)
            deadline, bundle_code, last_bundle, owned_pod = time.monotonic() + config['timeout_seconds'], None, None, None
            while time.monotonic() < deadline:
                current = object_json(config, 'get', 'kusciajob', '-n', 'cross-domain', name)
                if current['metadata']['uid'] != uid:
                    raise RuntimeError('The suite job identity changed')
                task = object_json(config, 'get', 'kusciatask', '-n', 'cross-domain', run_id, check=False)
                if task:
                    pods = object_json(config, 'get', 'pods', '-n', config['domain'], '-l',
                                       'kuscia.secretflow/task-uid=' + task['metadata']['uid'])['items']
                    if len(pods) > 1:
                        raise RuntimeError('Unexpected suite pod count')
                    if pods:
                        if owned_pod and owned_pod['metadata']['uid'] != pods[0]['metadata']['uid']:
                            raise RuntimeError('The suite pod identity changed')
                        owned_pod = pods[0]
                if owned_pod:
                    logs = pod_logs(config, owned_pod, run_id)
                    if logs is not None:
                        content, transport = logs
                        private_write(destination / 'task.log', content)
                        private_write(destination / 'log-transport.json', (json.dumps({
                            'transport': transport, 'pod': owned_pod['metadata']['name'],
                            'pod_uid': owned_pod['metadata']['uid']}) + '\n').encode())
                        for kind, path, payload in frames(content.decode(errors='replace'), run_id):
                            if kind == 'FILE' and last_bundle is None:
                                private_write(destination / path, payload)
                            elif kind == 'BUNDLE':
                                sha = hashlib.sha256(payload).hexdigest()
                                if sha != last_bundle:
                                    bundle_code = unpack_bundle(payload, destination, run_id)
                                    last_bundle = sha
                phase = current.get('status', {}).get('phase')
                if phase in terminal:
                    completed = True
                    if phase != 'Succeeded' or bundle_code != 0 or not verified_reports(destination, run_id):
                        raise RuntimeError('Kuscia suite failed or its numeric/protocol results were incomplete: ' + str(phase))
                    result_code = 0
                    print('All eight numerical and protocol checks passed through Kuscia.', flush=True)
                    return
                time.sleep(3)
            raise RuntimeError('Kuscia suite exceeded 900 seconds')
        finally:
            if uid and not completed:
                cancel_own_job(config, name, uid)
            private_write(destination / 'exit-code', (str(result_code) + '\n').encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='action', required=True)
    setup = subparsers.add_parser('install')
    setup.add_argument('--runtime-root', type=Path, default=Path('/opt/ppci'))
    setup.add_argument('--image-ref', required=True)
    setup.add_argument('--image-tag', required=True)
    setup.add_argument('--image-id', required=True)
    setup.add_argument('--container', default='gaofeng-kuscia-autonomy-alice')
    setup.add_argument('--domain', default='alice')
    run = subparsers.add_parser('run')
    run.add_argument('run_id')
    run.add_argument('--runtime-root', type=Path, default=Path('/opt/ppci'))
    args = parser.parse_args()
    os.umask(0o077)
    def interrupted(signum, frame):
        raise InterruptedError('Suite runner interrupted')
    signal.signal(signal.SIGTERM, interrupted)
    try:
        install(args) if args.action == 'install' else execute(args)
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print('BFIA suite: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
