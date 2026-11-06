#!/usr/bin/env python3
"""Stream stopped source containers to the explicitly selected migration host.

No local image snapshots. Partial archives are never accepted as backups.
Container configuration and bind-mounted data must be transferred separately.
"""
import argparse
import json
from pathlib import Path
import subprocess

ap = argparse.ArgumentParser()
ap.add_argument('--manifest', required=True)
ap.add_argument('--ssh-socket', required=True)
ap.add_argument('--host', required=True)
ap.add_argument('--port', default='2222')
ap.add_argument('--destination', required=True)
args = ap.parse_args()
ssh = ['ssh', '-S', args.ssh_socket, '-p', args.port, args.host]
import shlex
def remote(command):
    return subprocess.run(ssh + [command], check=True)

for c in json.loads(Path(args.manifest).read_text()):
    name = c['Name'].lstrip('/')
    image = c['Config']['Image']
    if not image.startswith(('secretflow/kuscia:', 'federatedai/', 'paddledtx-dai:', 'registry.baidubce.com/')):
        continue
    dest = args.destination + '/' + name + '-rootfs.tar.gz'
    q = shlex.quote(dest)
    if subprocess.run(ssh + ['test -s ' + q + ' && test -s ' + q + '.sha256']).returncode == 0:
        print('Already backed up ' + name, flush=True)
        continue
    state = subprocess.check_output(['docker', 'inspect', '-f', '{{.State.Running}}', name], text=True).strip()
    if state != 'false':
        raise RuntimeError('Refusing inconsistent backup of running container ' + name)
    print('Exporting ' + name, flush=True)
    a = subprocess.Popen(['docker', 'export', name], stdout=subprocess.PIPE)
    b = subprocess.Popen(['gzip', '-1'], stdin=a.stdout, stdout=subprocess.PIPE)
    a.stdout.close()
    d = subprocess.Popen(ssh + ['umask 077; cat > ' + q + '.partial'], stdin=b.stdout)
    b.stdout.close()
    codes = [d.wait(), b.wait(), a.wait()]
    if any(codes):
        raise RuntimeError('Backup incomplete: ' + name + ' ' + str(codes))
    remote('gzip -t ' + q + '.partial && mv ' + q + '.partial ' + q + ' && sha256sum ' + q + ' > ' + q + '.sha256')
    print('Verified backup ' + name, flush=True)
