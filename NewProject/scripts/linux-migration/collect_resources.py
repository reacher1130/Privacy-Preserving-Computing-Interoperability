#!/usr/bin/env python3.11
"""Capture project resource usage separately from the server's other services."""
import datetime
import json
from pathlib import Path
import re
import subprocess

def output(cmd):
    return subprocess.check_output(cmd, text=True, timeout=120).strip()
def size(value):
    m = re.fullmatch(r'([\d.]+)([A-Za-z]+)', value.strip())
    factors = {'B': 1, 'kB': 1000, 'KB': 1000, 'MB': 1000**2, 'GB': 1000**3, 'KiB': 1024, 'MiB': 1024**2, 'GiB': 1024**3}
    return int(float(m[1]) * factors[m[2]])
names = [v['Name'].lstrip('/') for v in json.loads(Path('/var/backups/ppci/migration-20260908/containers.json').read_text())]
rows = [json.loads(line) for line in output(['docker', 'stats', '--no-stream', '--format', '{{json .}}', *names]).splitlines()]
backends = []
for node in ('alice', 'bob', 'kimi'):
    pid = output(['systemctl', 'show', 'ppci-' + node, '-p', 'MainPID', '--value'])
    status = Path('/proc/' + pid + '/status').read_text()
    rss = int(re.search(r'^VmRSS:\s+(\d+)', status, re.M)[1]) * 1024
    backends.append({'node': node, 'pid': int(pid), 'rssBytes': rss})
paths = ['/opt/ppci', '/opt/ppci-build', '/opt/ppci-tools', '/srv/ppci', '/var/backups/ppci', '/var/log/ppci']
disk = {p: int(output(['du', '-sk', p]).split()[0]) * 1024 for p in paths}
data = {'time': datetime.datetime.now().astimezone().isoformat(), 'containers': rows, 'backends': backends,
        'containerWorkingSetBytes': sum(size(r['MemUsage'].split('/')[0]) for r in rows),
        'backendRssBytes': sum(v['rssBytes'] for v in backends), 'directoriesBytes': disk,
        'serverMemory': output(['free', '-h']), 'serverDisk': output(['df', '-h', '/'])}
data['projectMemoryEstimateBytes'] = data['containerWorkingSetBytes'] + data['backendRssBytes']
dest = Path('/opt/ppci/NewProject/docs/migration-20260908/resources-final.json')
dest.write_text(json.dumps(data, ensure_ascii=False, indent=2))
print(json.dumps({k:v for k,v in data.items() if k not in ('containers', 'backends')}, ensure_ascii=False, indent=2))
