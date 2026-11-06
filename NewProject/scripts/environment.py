#!/usr/bin/env python3
"""Explicit home/office source sync and remote build. Passwords stay in SSH."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[2]
CONFIG = Path(__file__).with_name('environments')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('environment', choices=('home', 'office'))
    p.add_argument('action', choices=('info', 'ssh', 'sync', 'build', 'deploy', 'status'))
    p.add_argument('component', nargs='?', choices=('backend', 'frontend', 'kimi'))
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--control-path', default=os.environ.get('PPCI_SSH_CONTROL_PATH'))
    a = p.parse_args()
    env = json.loads((CONFIG / (a.environment + '.json')).read_text())
    ssh = ['ssh', '-p', str(env['ssh_port']), '-o', 'ConnectTimeout=10']
    if a.control_path:
        ssh += ['-S', a.control_path]
    target = env['ssh_user'] + '@' + env['host']
    source = env['source_root']
    if a.action == 'info':
        print(json.dumps(env, indent=2))
        for name, port in [('Alice', 18101), ('Bob', 28101), ('Kimi', 38101), ('FATEBoard Guest', 19383), ('PaddleDTX', 18511)]:
            print(f'{name}: http://{env["host"]}:{port}')
        if a.environment == 'office':
            print(f'FATEBoard Host: http://{env["host"]}:19384')
        return
    if a.action == 'ssh':
        cmd = ssh + [target]
    elif a.action == 'sync':
        # Runtime identities, databases, build caches and datasets are never synced.
        excludes = ['.DS_Store', 'node_modules', 'target', 'testdatatmp', 'bazel-*', '__pycache__', '.codegraph', '.learnings',
                    '.local-backups', '.runtime', '*.sqlite*', '*.mv.db', '*.trace.db',
                    '*.log', '.ssh', '.env.local', '.env.*.local', 'config/certs', 'server.jks', '/privacy-computing-interconnectivity',
                    '/gaofeng-kuscia-autonomy-*', '/kuscia-node-bob']
        cmd = ['rsync', '-a', '--no-owner', '--no-group', '--stats']
        if a.dry_run:
            cmd += ['--dry-run', '--itemize-changes']
        cmd += ['--exclude=' + item for item in excludes]
        cmd += ['-e', shlex.join(ssh), str(ROOT) + '/', target + ':' + source + '/']
    elif a.action in ('build', 'deploy'):
        if not a.component:
            p.error(a.action + ' requires backend, frontend or kimi')
        script = 'build-platform.sh' if a.action == 'build' else 'deploy-built.sh'
        command = ['env', 'PPCI_SOURCE_ROOT=' + source, 'PPCI_BUILD_ROOT=' + env['build_root'],
                   'PPCI_ROOT=' + env['runtime_root'],
                   'bash', source + '/NewProject/scripts/linux-migration/' + script, a.component]
        cmd = ssh + [target, shlex.join(command)]
    else:
        cmd = ssh + [target, 'ppci-platform status']
    print(shlex.join(cmd), flush=True)
    if a.dry_run and a.action != 'sync':
        return
    subprocess.run(cmd, check=True)


if __name__ == '__main__':
    main()
