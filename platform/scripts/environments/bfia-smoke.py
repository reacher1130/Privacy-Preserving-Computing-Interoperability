#!/usr/bin/env python3
"""Verify BFIA PSI through the real Alice/Bob Kuscia transport using generated samples."""
import csv
import datetime
import json
import os
from pathlib import Path
import subprocess
import time

import yaml

SOURCE = Path(os.environ.get('PPCI_SOURCE_ROOT', '/opt/ppci-source'))


def kubectl(node, *args, data=None):
    return subprocess.check_output(['docker', 'exec', '-i', 'gaofeng-kuscia-autonomy-' + node,
                                   'kubectl', *args], input=data, text=True)


def main():
    stamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    name = 'home-bfia-psi-' + stamp
    task_id = name + '-psi'
    out = Path('/var/log/ppci') / ('acceptance-bfia-' + stamp)
    out.mkdir()
    template = SOURCE / 'platform/kuscia/scripts/user/bfia/job-ecdh-psi.yaml'
    job = yaml.safe_load(template.read_text())
    job['metadata']['name'] = name
    task = job['spec']['tasks'][0]
    task['taskID'] = task_id
    cfg = json.loads(task['taskInputConfig'])
    cfg['task_params']['common']['field_names'] = 'id'
    for node, role, content in [('alice', 'host', 'id,value\n1,10\n2,20\n3,30\n'),
                                ('bob', 'guest', 'id,value\n2,200\n3,300\n4,400\n')]:
        filename = name + '-' + node + '.csv'
        (out / filename).write_text(content)
        subprocess.run(['docker', 'cp', str(out / filename), 'gaofeng-kuscia-autonomy-' + node +
                        ':/home/kuscia/var/storage/data/' + filename], check=True)
        cfg['task_params'][role]['0'] = {'name': filename, 'namespace': 'data'}
    task['taskInputConfig'] = json.dumps(cfg)
    (out / 'job.json').write_text(json.dumps(job, indent=2))
    print(kubectl('alice', 'apply', '-f', '-', data=json.dumps(job)), flush=True)
    print('EVIDENCE=' + str(out), flush=True)
    for _ in range(120):
        result = json.loads(kubectl('alice', 'get', 'kj', '-n', 'cross-domain', name, '-o', 'json'))
        (out / 'status.json').write_text(json.dumps(result, indent=2))
        phase = result.get('status', {}).get('phase', '')
        print('STATUS=' + phase, flush=True)
        if phase in ('Succeeded', 'Failed', 'Cancelled'):
            for node, role in [('alice', 'host'), ('bob', 'guest')]:
                container = 'gaofeng-kuscia-autonomy-' + node
                output_path = f'/home/kuscia/var/storage/{name}-{role}-0/{task_id}-result'
                subprocess.run(['docker', 'cp', container + ':' + output_path,
                                str(out / (node + '-output.csv'))], check=False)
                logs = Path(f'/var/lib/docker/volumes/ppci-kuscia-{node}-var/_data/stdout/pods')
                for f in logs.glob(node + '_' + task_id + '-*/**/0.log'):
                    (out / (node + '-engine.log')).write_bytes(f.read_bytes())
            if phase != 'Succeeded': raise RuntimeError('BFIA Kuscia job did not succeed')
            for node in ('alice', 'bob'):
                with (out / (node + '-output.csv')).open() as stream:
                    rows = list(csv.DictReader(stream))
                if len(rows) != 2 or {r['id'] for r in rows} != {'2', '3'}:
                    raise RuntimeError('BFIA output differs from expected intersection: ' + node)
            print('OUTPUT_CHECK=PASS intersection=2,3', flush=True)
            return
        time.sleep(5)
    raise TimeoutError('BFIA PSI exceeded ten minutes; job and evidence retained')


if __name__ == '__main__':
    main()
