#!/usr/bin/env python3.11
"""Manage only the migrated PPCI platform, leaving other server services alone."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = Path('/var/backups/ppci/migration-20260908/containers.json')
NAMES = [v['Name'].lstrip('/') for v in json.loads(MANIFEST.read_text())]
if Path('/srv/ppci/dtx-manager/conf/app.conf').is_file():
    NAMES.append('ppci-dtx-manager')
UNITS = ['ppci-' + n for n in ('alice', 'bob', 'kimi')]
ap = argparse.ArgumentParser()
ap.add_argument('action', choices=['start', 'stop', 'restart', 'status'])
args = ap.parse_args()
def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)
def wait_ready():
    deadline = time.monotonic() + 360
    while time.monotonic() < deadline:
        try:
            for port in (18080, 28090, 38090):
                path = '/api/v1alpha1/config/protocol' if port != 38090 else '/api/v1alpha1/node/list'
                req = urllib.request.Request('http://127.0.0.1:' + str(port) + path,
                        data=b'{}' if port == 38090 else None, headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(req, timeout=5) as res:
                    assert json.load(res)['status']['code'] == 0
            return
        except Exception:
            time.sleep(5)
    raise RuntimeError('Platform backends did not become ready within 360 seconds')
if args.action in ('stop', 'restart'):
    run(['systemctl', 'stop', *UNITS])
    run(['docker', 'stop', '-t', '30', *NAMES])
if args.action in ('start', 'restart'):
    run(['docker', 'start', *NAMES])
    run(['systemctl', 'start', *UNITS])
    wait_ready()
if args.action != 'stop':
    env = dict(os.environ, USER='gaofeng')
    raise SystemExit(subprocess.call(['/usr/bin/python3.11', str(ROOT / 'NewProject/scripts/platform_runtime.py'), 'status'], env=env))
