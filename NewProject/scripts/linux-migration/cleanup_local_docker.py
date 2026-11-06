#!/usr/bin/env python3
"""Remove only the stopped Docker resources inventoried for this migration."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKUP = ROOT / 'NewProject/.local-backups/migration-20260908'
REPORT = ROOT / 'NewProject/docs/migration-20260908/local-docker-cleanup.json'

def run(*args):
    return subprocess.check_output(args, text=True).strip()

def inspect(kind, ids):
    return json.loads(run('docker', kind, 'inspect', *ids)) if ids else []

names = {c['Name'].lstrip('/') for c in json.loads((BACKUP / 'containers.json').read_text())}
containers = inspect('container', run('docker', 'ps', '-aq').split())
owned = [c for c in containers if c['Name'].lstrip('/') in names]
others = [c for c in containers if c not in owned]
assert len(owned) == 28, 'Unexpected project container inventory'
assert all(not c['State']['Running'] for c in owned), 'Project containers must be stopped'
other_images = {c['Image'] for c in others}
other_volumes = {m['Name'] for c in others for m in c['Mounts'] if m['Type'] == 'volume'}
volumes = {m['Name'] for c in owned for m in c['Mounts'] if m['Type'] == 'volume'}
assert volumes.isdisjoint(other_volumes)
assert all(v.startswith('gaofeng-kuscia-autonomy-') and v.endswith('-containerd') for v in volumes)
images = sorted(inspect('image', sorted(set(run('docker', 'images', '-aq').split()))),
                key=lambda i: len(i['RootFS']['Layers']), reverse=True)
shared_tags = {'nginx:1.27', 'arm64v8/nginx:1.27', 'alpine/socat:latest'}
owned_image_ids = {c['Image'] for c in owned if c['Config']['Image'] not in shared_tags}
algorithm_tags = {
    'secretflow-registry.cn-hangzhou.cr.aliyuncs.com/secretflow/' + tag
    for tag in ['bfia-cpp-runtime:linux-amd64-slim', 'morse-ecdh-header:20251113',
                'ecdh:latest', 'ecdh-psi:latest', 'ss-lr:latest', 'ss-xgb:latest',
                'ss-pearson:latest', 'ss-vif:latest', 'ss-compare:latest']}
tags = [tag for i in images if i['Id'] not in other_images
        for tag in (i.get('RepoTags') or [])
        if tag not in shared_tags and (i['Id'] in owned_image_ids or tag in algorithm_tags)]
report = {'containers': sorted(names), 'volumes': sorted(volumes), 'imageTags': tags,
          'retainedContainers': {c['Name']: c['Id'] for c in others}, 'completed': False}
REPORT.write_text(json.dumps(report, indent=2))
if '--execute' not in sys.argv:
    print(json.dumps(report, indent=2))
    raise SystemExit(0)
run('docker', 'container', 'rm', *[c['Id'] for c in owned])
run('docker', 'volume', 'rm', *sorted(volumes))
removed_tags = []
retained_tags = {}
for tag in tags:
    result = subprocess.run(['docker', 'image', 'rm', tag], text=True, capture_output=True)
    if result.returncode == 0:
        removed_tags.append(tag)
    else:
        retained_tags[tag] = result.stderr.strip()
after = inspect('container', run('docker', 'ps', '-aq').split())
assert {c['Name']: c['Id'] for c in after} == report['retainedContainers']
assert not any(v in run('docker', 'volume', 'ls', '-q').split() for v in volumes)
report['completed'] = True
report['removedImageTags'] = removed_tags
report['retainedImageTags'] = retained_tags
REPORT.write_text(json.dumps(report, indent=2))
print(json.dumps({'removedContainers': len(owned), 'removedVolumes': len(volumes),
                  'removedImageTags': len(removed_tags), 'otherContainersUnchanged': True,
                  'retainedImageTags': retained_tags}))
