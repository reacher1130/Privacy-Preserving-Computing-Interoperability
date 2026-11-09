#!/usr/bin/env python3
"""Real public Boston train/predict smoke; approve only this run's exact file/task/executor."""
import argparse
import csv
import datetime
import hashlib
import io
import json
import math
from pathlib import Path
import re
import subprocess
import time
import uuid

UUID = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'


def command(*args):
    result = subprocess.run(list(map(str, args)), capture_output=True, text=True, timeout=120)
    text = result.stdout + result.stderr
    # Several historical Go CLIs report application errors with exit status zero.
    if result.returncode or re.search(r'(?im)^(?:err(?:or)?[：:]|.*\bfailed[：:]|Error:)', text):
        raise RuntimeError('PaddleDTX command failed: ' + ' '.join(map(str, args[:4])) + '\n' + text[-4000:].strip())
    return result.stdout


def owner(node, *args):
    return command('docker', 'exec', f'dataowner{node}.node.com', './xdb-cli', 'files', *args,
                   '--host', f'http://dataowner{node}.node.com:80', '--keyPath', './ukeys')


def requester(*args):
    keys = ('--keyPath', './reqkeys') if args[0] in ('publish', 'start', 'result') else ()
    return command('docker', 'exec', 'executor1.node.com', '/home/requester-cli-current', 'task', *args,
                   '--conf', './conf/requester-config.toml', *keys)


def field(text, key):
    found = re.search(r'^' + re.escape(key) + r':\s*(.*?)\s*$', text, re.M)
    if not found:
        raise RuntimeError('Missing PaddleDTX output field: ' + key)
    return found.group(1)


def matching_auths(text, task, file_id, applier):
    matches = []
    for block in re.split(r'(?=^AuthID:)', text, flags=re.M):
        if not block.startswith('AuthID:'):
            continue
        if (field(block, 'Name') == 'TaskID-' + task and field(block, 'FileID') == file_id
                and field(block, 'Applier') == applier and field(block, 'Status') == 'Unapproved'):
            auth = field(block, 'AuthID')
            if not re.fullmatch(UUID, auth):
                raise RuntimeError('Invalid authorization UUID')
            matches.append(auth)
    return matches


def validate_prediction(text, expected):
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames != ['id', 'value']:
        raise RuntimeError('Prediction must contain id,value CSV')
    rows = list(reader)
    ids = [row['id'] for row in rows]
    if not rows or len(set(ids)) != len(ids) or set(ids) != expected:
        raise RuntimeError('Prediction IDs do not equal the public input intersection')
    if any(not math.isfinite(float(row['value'])) for row in rows):
        raise RuntimeError('Prediction contains nonfinite values')
    return {'rows': len(rows), 'idsEqualInputIntersection': True, 'allValuesFinite': True,
            'sha256': hashlib.sha256(text.encode()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Private run directory; reuse to resume existing task UUIDs')
    parser.add_argument('--timeout', type=int, default=900)
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error('--timeout must be positive')
    run_id = uuid.uuid4().hex
    out = args.output or Path('/var/log/ppci') / ('paddle-smoke-' + run_id)
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker = out / 'summary.json'
    state = json.loads(marker.read_text()) if marker.exists() else {'runId': run_id, 'files': {}, 'tasks': {}, 'pass': False}
    def save():
        marker.write_text(json.dumps(state, indent=2) + '\n')
        marker.chmod(0o600)
    save()
    expires = (datetime.datetime.now() + datetime.timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
    for kind in ('train', 'predict'):
        if kind not in state['files'] or len(state['files'][kind]) < 2:
            namespace = 'ppci_smoke_' + state['runId'] + '_' + kind
            files = state['files'].setdefault(kind, [])
            namespaces = state.setdefault('namespaces', {}).setdefault(kind, [])
            for node, suffix in ((1, 'A'), (2, 'B')):
                if len(files) >= node:
                    continue
                if node not in namespaces:
                    if owner(node, 'addns', '-n', namespace, '-r', '2').strip() != 'OK':
                        raise RuntimeError('Could not create isolated public sample namespace')
                    namespaces.append(node)
                    save()
                features = 'id,CRIM,ZN,INDUS,CHAS,NOX,RM' if node == 1 else 'id,AGE,DIS,RAD,TAX,PTRATIO,B,LSTAT' + (',MEDV' if kind == 'train' else '')
                text = owner(node, 'upload', '-e', expires, '-n', namespace, '-m', kind + suffix,
                             '--ext', json.dumps({'fileType': 'csv', 'features': features, 'totalRows': 456 if kind == 'train' else 50}),
                             '-i', f'/home/mpc-data/linear_boston_housing/{kind}_data{suffix}.csv',
                             '-d', 'PPCI isolated public repository algorithm fixture')
                file_id = field(text, 'FileID')
                if not re.fullmatch(UUID, file_id):
                    raise RuntimeError('Upload did not return a file UUID; XDB storage may not yet be eligible')
                files.append(file_id)
                save()
        files = state['files'][kind]
        if kind not in state['tasks']:
            params = ['publish', '-n', 'ppci_' + kind + '_' + state['runId'], '-t', kind,
                      '-a', 'linear-vl', '-f', ','.join(files), '-e', 'executor1,executor2', '-p', 'id,id']
            params += ['-l', 'MEDV', '--amplitude', '0.0001'] if kind == 'train' else ['-i', state['tasks']['train']]
            task = field(requester(*params), 'TaskID')
            if not re.fullmatch(UUID, task):
                raise RuntimeError('Publish did not return task UUID; check task history before retrying')
            state['tasks'][kind] = task
            save()
        task = state['tasks'][kind]
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            snapshot = requester('getbyid', '-i', task)
            status = field(snapshot, 'Status')
            if status == 'Finished':
                break
            if status in ('Failed', 'Rejected'):
                raise RuntimeError('Task ' + task + ' ended as ' + status + '; original task retained')
            if status == 'Confirming':
                for node, file_id in enumerate(files, 1):
                    applier = command('docker', 'exec', f'executor{node}.node.com', 'cat', '/home/keys/public.key').strip()
                    applications = owner(node, 'listauth', '--status', 'Unapproved', '-f', file_id, '-a', applier)
                    for auth in matching_auths(applications, task, file_id, applier):
                        expiry = (datetime.datetime.now() + datetime.timedelta(hours=2)).strftime('%Y-%m-%d %H:%M:%S')
                        if owner(node, 'confirmauth', '-i', auth, '-e', expiry).strip() != 'OK':
                            raise RuntimeError('Scoped public sample authorization failed')
            if status == 'Ready':
                if requester('start', '-i', task).strip() != 'OK':
                    raise RuntimeError('Task start failed; resume using --output ' + str(out))
            time.sleep(3)
        else:
            raise RuntimeError('Task ' + task + ' timed out; resume the SAME task with --output ' + str(out))
        if kind == 'train':
            state['models'] = []
            for node in (1, 2):
                model = command('docker', 'exec', f'executor{node}.node.com', 'cat', '/home/models/' + task)
                if not model.strip():
                    raise RuntimeError('Training model is missing from executor ' + str(node))
                state['models'].append({'executor': node, 'bytes': len(model.encode()), 'sha256': hashlib.sha256(model.encode()).hexdigest()})
            save()
    task = state['tasks']['predict']
    path = '/tmp/ppci-prediction-' + task + '.csv'
    if requester('result', '-i', task, '-o', path).strip() != 'OK':
        raise RuntimeError('Signed prediction result readback failed')
    result = command('docker', 'exec', 'executor1.node.com', 'cat', path)
    expected = None
    for node, suffix in ((1, 'A'), (2, 'B')):
        text = command('docker', 'exec', f'dataowner{node}.node.com', 'cat', f'/home/mpc-data/linear_boston_housing/predict_data{suffix}.csv')
        ids = {row['id'] for row in csv.DictReader(io.StringIO(text))}
        expected = ids if expected is None else expected & ids
    state['prediction'] = validate_prediction(result, expected)
    state['pass'] = True
    save()
    print(marker)


if __name__ == '__main__':
    main()
