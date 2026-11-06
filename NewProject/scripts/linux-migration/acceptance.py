#!/usr/bin/env python3
"""Run representative migrated workflows and persist API evidence on Linux."""
import argparse
import json
from pathlib import Path
import urllib.request

root = Path('/opt/ppci')
out = root / 'NewProject/docs/migration-20260908'
out.mkdir(parents=True, exist_ok=True)
old = root / 'NewProject/docs/optimization-20260908'
ap = argparse.ArgumentParser()
ap.add_argument('action', choices=['bfia-submit', 'bfia-status', 'native-submit', 'native-status', 'paddle-submit', 'paddle-status', 'fate-submit', 'fate-status'])
args = ap.parse_args()
def call(path, data=None, timeout=240):
    endpoint = path if path.startswith('/api/') else '/api/v1alpha1/' + path
    req = urllib.request.Request('http://127.0.0.1:18080' + endpoint,
          data=None if data is None else json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.load(res)
bfia = {'projectId': '5570643997524d91b93997d7fd09966f', 'graphId': 'iqdcehaj'}
native = json.loads((old / 'native-request.json').read_text())
if args.action == 'bfia-submit':
    data = dict(bfia, nodes=['iqdcehaj-node-a', 'iqdcehaj-node-b', 'iqdcehaj-node-psi'], breakpoint=False)
    response = call('/api/v1bfia/flow/start', data)
elif args.action == 'bfia-status':
    response = call('/api/v1bfia/flow/node/status', bfia)
elif args.action == 'native-submit':
    response = call('graph/start', native)
elif args.action == 'native-status':
    response = call('graph/node/status', {k: native[k] for k in ('projectId', 'graphId')})
elif args.action == 'paddle-submit':
    data = json.loads((old / 'paddle-request.json').read_text())
    data['name'] = 'linux-migration-predict-20260908'
    response = call('paddledtx/task/submit', data)
elif args.action == 'paddle-status':
    task = json.loads((out / 'paddle-submit.json').read_text())['data']['taskId']
    response = call('paddledtx/task/get?taskId=' + task)
elif args.action == 'fate-submit':
    data = json.loads((old / 'fate-request.json').read_text())
    data['name'] = 'linux-migration-native-fate-20260908'
    response = call('fate/job/submit', data)
else:
    job = json.loads((out / 'fate-submit.json').read_text())['data']['jobId']
    response = call('fate/job/get?jobId=' + job)
(out / (args.action + '.json')).write_text(json.dumps(response, indent=2, ensure_ascii=False))
print(json.dumps(response, ensure_ascii=False))
if response.get('status', {}).get('code') != 0:
    raise SystemExit(1)
