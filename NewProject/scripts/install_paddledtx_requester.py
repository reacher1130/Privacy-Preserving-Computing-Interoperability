#!/usr/bin/env python3
"""Build and install the office custom requester metadata compatibility fix.

Run on the office Linux server. Preserve the original runtime source, ledger,
metadata, container identities and old CLI binaries.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

SOURCE = Path('/opt/ppci/privacy-computing-interconnectivity/shared-exchange-Connectivity/PaddleDTX/dai')
BUILD = Path('/opt/ppci-build/paddledtx-requester')
BACKUP = Path('/var/backups/ppci/office-recovery-20261102/requester-tools')
PATCH = Path(__file__).resolve().parent / 'patches/paddledtx-file-metadata.patch'
GO = '/opt/ppci-tools/go124/go/bin/go'
ORIGINAL_SHA = '8a63fd378401c975f43a8758e5aca520d4f640bc8c6c1fc1945b8c2f4191ee1a'
BINARY = '/home/requester-cli-demo'


def run(args, cwd=None, env=None):
    result = subprocess.run([str(x) for x in args], cwd=str(cwd) if cwd else None,
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            universal_newlines=True)
    if result.returncode:
        raise RuntimeError('Command failed: ' + ' '.join(str(x) for x in args[:3]) +
                           ' (output suppressed)')
    return result.stdout


def remote_sha(name, path):
    return run(['docker', 'exec', name, 'sha256sum', path]).split()[0]


def task_ids(name):
    output = run(['docker', 'exec', name, BINARY, '-c', '/home/conf/requester-config.toml', 'task', 'list'])
    ids = set(re.findall(r'(?m)^TaskID:\s*([0-9a-f-]{36})\s*$', output))
    if not ids:
        raise RuntimeError('Expected existing office tasks; refusing to accept empty CLI output')
    return ids


def main():
    if os.geteuid() != 0:
        raise RuntimeError('Run on the office Linux server as root')
    assert (BACKUP.parent / 'xchain1-rootfs-before.tar.gz').is_file(), 'Pre-change ledger backup missing'
    BACKUP.mkdir(mode=0o700, parents=True, exist_ok=True)
    BACKUP.chmod(0o700)
    BUILD.mkdir(mode=0o700, parents=True, exist_ok=True)
    BUILD.chmod(0o700)
    run(['rsync', '-a', '--delete', '--exclude=/.git', '--exclude=/executor.local',
         '--exclude=/requester-cli-linux-amd64', str(SOURCE) + '/', str(BUILD) + '/'])
    run(['git', 'apply', '--check', PATCH], cwd=BUILD)
    run(['git', 'apply', PATCH], cwd=BUILD)
    env = os.environ.copy()
    env.update(GOENV='off', GOPROXY='off', GOTOOLCHAIN='local', CGO_ENABLED='0', GOFLAGS='-mod=vendor')
    candidate = BACKUP / 'requester-cli-metadata-20261102'
    log = Path('/var/log/ppci/paddledtx-requester-build-20261102.log')
    with log.open('w') as out:
        for args in ([GO, 'test', '-p', '2', './util/filemeta', '-count=1'],
                     [GO, 'build', '-p', '2', './executor/handler'],
                     [GO, 'build', '-p', '2', '-ldflags=-s -w', '-o', str(candidate), './requester/cmd']):
            result = subprocess.run(args, cwd=str(BUILD), env=env, stdout=out, stderr=subprocess.STDOUT)
            if result.returncode:
                raise RuntimeError('Custom requester build/test failed; inspect ' + str(log))
    expected = hashlib.sha256(candidate.read_bytes()).hexdigest()
    rows = []
    for name in ('executor1.node.com', 'executor2.node.com'):
        before = remote_sha(name, BINARY)
        if before not in (ORIGINAL_SHA, expected):
            raise RuntimeError('Unrecognized requester binary retained: ' + name)
        old_ids = task_ids(name)
        original = BACKUP / (name + '.requester-cli-demo.before')
        if not original.exists():
            if before != ORIGINAL_SHA:
                raise RuntimeError('Original binary backup is missing')
            run(['docker', 'cp', name + ':' + BINARY, original])
            original.chmod(0o600)
        assert hashlib.sha256(original.read_bytes()).hexdigest() == ORIGINAL_SHA
        if before != expected:
            # shortcut: legacy executor images stay unchanged; rerun after recreating those containers.
            run(['docker', 'cp', candidate, name + ':' + BINARY + '.metadata-20261102'])
            run(['docker', 'exec', name, 'chmod', '755', BINARY + '.metadata-20261102'])
            run(['docker', 'exec', name, 'mv', BINARY + '.metadata-20261102', BINARY])
        after = remote_sha(name, BINARY)
        if after != expected or task_ids(name) != old_ids:
            run(['docker', 'cp', original, name + ':' + BINARY + '.restore-20261102'])
            run(['docker', 'exec', name, 'chmod', '755', BINARY + '.restore-20261102'])
            run(['docker', 'exec', name, 'mv', BINARY + '.restore-20261102', BINARY])
            raise RuntimeError('Requester check failed; original binary restored for ' + name)
        rows.append({'container': name, 'before_sha256': before, 'after_sha256': after,
                     'existing_task_count': len(old_ids), 'backup': str(original)})
    record = {'custom_source': str(SOURCE), 'patch_sha256': hashlib.sha256(PATCH.read_bytes()).hexdigest(),
              'binary_sha256': expected, 'bytes': candidate.stat().st_size, 'deployments': rows,
              'metadata_changed': False, 'contracts_changed': False, 'task_published': False}
    target = BACKUP / 'requester-deployment.json'
    target.write_text(json.dumps(record, indent=2))
    target.chmod(0o600)
    print(json.dumps(record))


if __name__ == '__main__':
    main()
