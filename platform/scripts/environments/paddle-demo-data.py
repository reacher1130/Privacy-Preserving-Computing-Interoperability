#!/usr/bin/env python3
"""Register the repository's public Boston sample with the two local data owners."""
import datetime
import json
from pathlib import Path
import re
import subprocess

OUT = Path('/var/log/ppci/acceptance-platform-20260912')


def cli(node, *args):
    p = subprocess.run(['docker', 'exec', f'dataowner{node}.node.com', './xdb-cli', 'files',
                        *args, '--host', f'http://dataowner{node}.node.com:80', '--keyPath', './ukeys'],
                       capture_output=True, text=True, timeout=120)
    text = p.stdout + p.stderr
    print(text, flush=True)
    if p.returncode or re.search(r'(?i)error|failed', text):
        raise RuntimeError('XDB command failed')
    return text


def main():
    OUT.mkdir(exist_ok=True)
    marker = OUT / 'paddle-datasets.json'
    if marker.exists():
        print(marker.read_text())
        return
    stamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    namespace = 'ppci_home_' + stamp
    expires = (datetime.datetime.now() + datetime.timedelta(days=180)).strftime('%Y-%m-%d %H:%M:%S')
    files = []
    for node, suffix, features in [(1, 'A', 'id,CRIM,ZN,INDUS,CHAS,NOX,RM'),
                                  (2, 'B', 'id,AGE,DIS,RAD,TAX,PTRATIO,B,LSTAT,MEDV')]:
        cli(node, 'addns', '-n', namespace, '-r', '2')
        output = cli(node, 'upload', '-e', expires, '-n', namespace, '-m', 'public_boston_' + suffix,
                     '--ext', json.dumps({'fileType': 'csv', 'features': features, 'totalRows': 457}),
                     '-i', '/home/mpc-data/linear_boston_housing/train_data' + suffix + '.csv',
                     '-d', 'PPCI home acceptance - public repository fixture')
        matches = re.findall(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', output)
        if not matches: raise RuntimeError('No uploaded file ID')
        files.append(matches[-1])
    marker.write_text(json.dumps({'namespace': namespace, 'files': files,
                                'executors': 'executor1,executor2', 'label': 'MEDV'}, indent=2))
    print(marker.read_text())


if __name__ == '__main__':
    main()
