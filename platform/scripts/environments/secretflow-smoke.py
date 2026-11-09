#!/usr/bin/env python3
"""Run native Alice/Kimi PSI on tiny generated, non-private sample tables."""
import datetime
import csv
import json
import os
from pathlib import Path
import subprocess
import time

SOURCE = Path(os.environ.get('PPCI_SOURCE_ROOT', '/opt/ppci-source'))


def kubectl(node, *args, data=None):
    return subprocess.check_output(['docker', 'exec', '-i', 'gaofeng-kuscia-autonomy-' + node,
                                    'kubectl', *args], input=data, text=True)


def apply(node, resource):
    print(kubectl(node, 'apply', '-f', '-', data=json.dumps(resource)), flush=True)


def main():
    stamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    job_id = 'home-native-psi-' + stamp
    out = Path('/var/log/ppci') / ('acceptance-secretflow-' + stamp)
    out.mkdir()
    ids = []
    for node, key, content, peer in [('alice', 'id1', 'id1,value\n1,10\n2,20\n3,30\n', 'kimi'),
                                      ('kimi', 'id2', 'id2,value\n2,200\n3,300\n4,400\n', 'alice')]:
        dataset_id = job_id + '-' + node
        ids.append(dataset_id)
        filename = dataset_id + '.csv'
        sample = out / filename
        sample.write_text(content)
        subprocess.run(['docker', 'cp', str(sample), 'gaofeng-kuscia-autonomy-' + node +
                        ':/home/kuscia/var/storage/data/' + filename], check=True)
        apply(node, {'apiVersion': 'kuscia.secretflow/v1alpha1', 'kind': 'DomainData',
                     'metadata': {'name': dataset_id, 'namespace': node,
                                  'labels': {'kuscia.secretflow/interconn-protocol-type': 'kuscia',
                                             'kuscia.secretflow/initiator': node,
                                             'kuscia.secretflow/domaindata-type': 'table',
                                             'kuscia.secretflow/domaindata-vendor': 'manual'}},
                     'spec': {'name': filename, 'type': 'table', 'relativeURI': filename,
                              'dataSource': 'default-data-source', 'vendor': 'manual', 'author': node,
                              'attributes': {'description': 'Generated public acceptance sample'},
                              'columns': [{'name': key, 'type': 'str'}, {'name': 'value', 'type': 'float'}]}})
        apply(node, {'apiVersion': 'kuscia.secretflow/v1alpha1', 'kind': 'DomainDataGrant',
                     'metadata': {'name': dataset_id + '-grant', 'namespace': node},
                     'spec': {'author': node, 'domainDataID': dataset_id, 'grantDomain': peer,
                              'limit': {'expirationTime': (datetime.datetime.now(datetime.timezone.utc) +
                                       datetime.timedelta(hours=1)).isoformat()}}})
    cfg = json.loads((SOURCE / 'platform/kuscia/scripts/templates/task_input_config.2pc_balanced_psi.json')
                     .read_text().replace('bob', 'kimi'))
    cfg['sf_input_ids'] = ids
    cfg['sf_output_ids'] = [job_id + '-output', job_id + '-report']
    cfg['sf_output_uris'] = [job_id + '-output.csv', job_id + '-report']
    job = {'apiVersion': 'kuscia.secretflow/v1alpha1', 'kind': 'KusciaJob',
           'metadata': {'name': job_id, 'namespace': 'cross-domain'},
           'spec': {'initiator': 'alice', 'scheduleMode': 'BestEffort', 'maxParallelism': 1,
                    'tasks': [{'taskID': job_id + '-psi', 'alias': 'psi', 'priority': 100,
                               'taskInputConfig': json.dumps(cfg), 'appImage': 'secretflow-image',
                               'parties': [{'domainID': 'alice'}, {'domainID': 'kimi'}]}]}}
    (out / 'job.json').write_text(json.dumps(job, indent=2))
    apply('alice', job)
    print('EVIDENCE=' + str(out), flush=True)
    for _ in range(180):
        result = json.loads(kubectl('alice', 'get', 'kj', '-n', 'cross-domain', job_id, '-o', 'json'))
        (out / 'status.json').write_text(json.dumps(result, indent=2))
        status = result.get('status', {}).get('phase', '')
        print('STATUS=' + status, flush=True)
        if status in ('Succeeded', 'Failed', 'Cancelled'):
            for node in ('alice', 'kimi'):
                subprocess.run(['docker', 'cp', 'gaofeng-kuscia-autonomy-' + node +
                                ':/home/kuscia/var/storage/data/' + job_id + '-output.csv',
                                str(out / (node + '-output.csv'))], check=False)
            if status != 'Succeeded': raise RuntimeError('SecretFlow PSI did not succeed')
            for node, key in [('alice', 'id1'), ('kimi', 'id2')]:
                with (out / (node + '-output.csv')).open() as stream:
                    rows = list(csv.DictReader(stream))
                if len(rows) != 2 or {row[key] for row in rows} != {'2', '3'}:
                    raise RuntimeError('PSI output differs from the known sample intersection: ' + node)
            print('OUTPUT_CHECK=PASS intersection=2,3', flush=True)
            return
        time.sleep(5)
    raise TimeoutError('SecretFlow PSI exceeded 15 minutes; inspect preserved job')


if __name__ == '__main__':
    main()
