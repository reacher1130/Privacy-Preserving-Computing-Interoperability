#!/usr/bin/env python3
"""Run native FATE 2.2 PSI and LR on official public demo tables.

This tests the native Guest/Host/Arbiter independently of the platform adapter.
It creates timestamped datasets and jobs and never deletes existing state.
"""
import datetime
import json
from pathlib import Path
import time
import urllib.request

PARTIES = {'guest': 'JG0100001100000010', 'host': 'JG0100001100000000'}
PORTS = {'guest': 19381, 'host': 19382}
STAMP = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S')
NAMESPACE = 'ppci_home_' + STAMP
OUT = Path('/var/log/ppci/acceptance-' + STAMP)


def request(role, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(f'http://127.0.0.1:{PORTS[role]}/v2/' + path, data=data,
                               headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(r, timeout=60) as response:
        result = json.load(response)
    if result.get('code') != 0:
        raise RuntimeError(result)
    return result


def wait(role, job_id):
    for _ in range(120):
        result = request(role, 'job/query?job_id=' + job_id)
        rows = result.get('data', [])
        states = {row['status'].lower() for row in rows}
        if states and states <= {'success'}:
            tasks = request(role, 'job/task/query?job_id=' + job_id)
            if not tasks.get('data') or any(t['status'].lower() != 'success' for t in tasks['data']):
                raise RuntimeError('Job succeeded without successful task evidence: ' + job_id)
            (OUT / (job_id + '-' + role + '.json')).write_text(json.dumps({'job': result, 'tasks': tasks}, indent=2))
            return
        if states & {'failed', 'canceled', 'timeout', 'rejected'}:
            raise RuntimeError(result)
        time.sleep(5)
    raise TimeoutError(job_id)


def upload(role, table, meta):
    # The upload endpoint defaults to four cores, above this demo's engine limit.
    providers = {}
    for name in ('fate_flow', 'fate'):
        providers[name] = next(p for p in request(role, 'provider/query?name=' + name)['data']
                               if p['device'] == 'local')
    local = {'role': 'local', 'party_id': ['0']}
    schema = {'schema_version': providers['fate_flow']['version'], 'kind': 'fate', 'dag': {
        'stage': 'default', 'parties': [local],
        'conf': {'scheduler_party_id': '0', 'cores': 1, 'computing_partitions': 1,
                 'task': {'engine_run': {'cores': 1}}},
        'tasks': {
            'upload_0': {'component_ref': 'upload', 'parties': [local],
                         'conf': {'provider': providers['fate_flow']['provider_name']}},
            'transformer_0': {'component_ref': 'dataframe_transformer', 'parties': [local],
                              'conf': {'provider': providers['fate']['provider_name']},
                              'inputs': {'data': {'table': {'task_output_artifact': {
                                  'producer_task': 'upload_0', 'output_artifact_key': 'table'}}}}}},
        'party_tasks': {'local_0': {'parties': [local], 'tasks': {
            'upload_0': {'parameters': {
                'file': '/data/projects/fate/examples/data/' + table + '.csv', 'head': True,
                'partitions': 1, 'extend_sid': True, 'is_temp_file': False, 'meta': meta}},
            'transformer_0': {'parameters': {'namespace': NAMESPACE, 'name': table}}}}}}}
    (OUT / ('upload-' + role + '-schema.json')).write_text(json.dumps(schema, indent=2))
    return request(role, 'job/submit', {'dag_schema': schema})


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for role in PARTIES:
        if request(role, 'site/info/query')['data']['party_id'] != PARTIES[role]:
            raise RuntimeError('Unexpected native party: ' + role)
        table = 'breast_hetero_' + role
        meta = {'delimiter': ',', 'match_id_name': 'id'}
        if role == 'guest': meta['label_name'] = 'y'
        result = upload(role, table, meta)
        print('UPLOAD', role, json.dumps(result), flush=True)
        (OUT / ('upload-' + role + '.json')).write_text(json.dumps(result, indent=2))
        if result.get('job_id'): wait(role, result['job_id'])
    data_parties = [{'role': role, 'party_id': [pid]} for role, pid in PARTIES.items()]
    party_tasks = {role + '_' + pid: {'parties': [party], 'tasks': {
        'reader_0': {'parameters': {'namespace': NAMESPACE, 'name': 'breast_hetero_' + role}}}}
        for (role, pid), party in zip(PARTIES.items(), data_parties)}
    results = {}
    for name in ('psi', 'lr'):
        parties = data_parties + ([{'role': 'arbiter', 'party_id': [PARTIES['host']]}] if name == 'lr' else [])
        tasks = {
            'reader_0': {'component_ref': 'reader', 'parties': data_parties, 'stage': 'default'},
            'psi_0': {'component_ref': 'psi', 'parties': data_parties, 'stage': 'default',
                      'parameters': {'protocol': 'ecdh_psi', 'curve_type': 'curve25519'},
                      'dependent_tasks': ['reader_0'], 'inputs': {'data': {'input_data': {
                          'task_output_artifact': {'producer_task': 'reader_0', 'output_artifact_key': 'output_data'}}}}}}
        if name == 'lr':
            tasks['lr_0'] = {'component_ref': 'coordinated_lr', 'parties': parties, 'stage': 'train',
                'parameters': {'epochs': 2, 'batch_size': 64}, 'dependent_tasks': ['psi_0'],
                'inputs': {'data': {'train_data': {'task_output_artifact': {
                    'producer_task': 'psi_0', 'output_artifact_key': 'output_data'}}}}}
        schema = {'schema_version': '2.0.0', 'kind': 'fate', 'dag': {'stage': 'train',
            'parties': parties, 'tasks': tasks, 'party_tasks': party_tasks, 'conf': {
                'scheduler_party_id': PARTIES['guest'], 'initiator_party_id': PARTIES['guest'],
                'cores': 1, 'computing_partitions': 1, 'task': {'engine_run': {'cores': 1}}}}}
        (OUT / (name + '-schema.json')).write_text(json.dumps(schema, indent=2))
        result = request('guest', 'job/submit', {'dag_schema': schema})
        job_id = result['job_id']
        print('SUBMIT', name, job_id, flush=True)
        results[name] = job_id
        for role in PARTIES: wait(role, job_id)
        print('PASS', name, job_id, flush=True)
    (OUT / 'summary.json').write_text(json.dumps({'namespace': NAMESPACE, 'jobs': results}, indent=2))
    print('EVIDENCE', OUT, flush=True)


if __name__ == '__main__':
    main()
