#!/usr/bin/env python3
"""Build/publish signed native-manager downloads, retaining old hashed assets."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

SOURCE = Path('/opt/ppci/privacy-computing-interconnectivity/shared-exchange-Connectivity/dtx-fe')
BUILD = Path('/opt/ppci-build/dtx-native-ui')
TOOLS = Path('/var/backups/ppci/office-recovery-20261102/native-download-tools')
PATCH = Path(__file__).resolve().parent / 'patches/paddledtx-native-download.patch'
INDEX = Path('static/unicom-dtx/page/index.html')
NODE = '/opt/ppci-tools/node20/bin'


def run(args, cwd=None):
    result = subprocess.run([str(x) for x in args], cwd=str(cwd) if cwd else None,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    if result.returncode:
        raise RuntimeError('Command failed: ' + ' '.join(str(x) for x in args[:3]))
    return result.stdout


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply_patch(directory):
    check = subprocess.run(['git', 'apply', '--check', str(PATCH)], cwd=str(directory),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check.returncode == 0:
        run(['git', 'apply', PATCH], cwd=directory)
    else:
        run(['git', 'apply', '--reverse', '--check', PATCH], cwd=directory)


def build():
    BUILD.mkdir(mode=0o700, parents=True, exist_ok=True)
    BUILD.chmod(0o700)
    run(['rsync', '-a', '--delete', '--exclude=/.git', '--exclude=/build', '--exclude=/node_modules',
         str(SOURCE) + '/', str(BUILD) + '/'])
    apply_patch(BUILD)
    env = os.environ.copy()
    env['PATH'] = NODE + ':' + env.get('PATH', '')
    env['NODE_OPTIONS'] = '--max-old-space-size=3072'
    log = Path('/var/log/ppci/dtx-native-ui-build-20261102.log')
    with log.open('w') as out:
        for args in ([NODE + '/npm', 'ci', '--ignore-scripts', '--legacy-peer-deps',
                      '--prefer-offline', '--no-audit', '--fund=false'],
                     [NODE + '/node', '--test', 'scripts/check-download.cjs'],
                     [NODE + '/npm', 'run', 'build']):
            result = subprocess.run(args, cwd=str(BUILD), env=env, stdout=out, stderr=subprocess.STDOUT)
            if result.returncode:
                raise RuntimeError('Native UI build/self-check failed; inspect ' + str(log))
    (TOOLS / 'verified-build.json').write_text(json.dumps({
        'patch_sha256': sha(PATCH), 'self_checks': 4, 'production_build_exit_code': 0,
        'index_sha256': sha(BUILD / 'build' / INDEX)}, indent=2))


def publish():
    verified = json.loads((TOOLS / 'verified-build.json').read_text())
    candidate = BUILD / 'build'
    assert verified['patch_sha256'] == sha(PATCH)
    assert verified['production_build_exit_code'] == 0 and verified['self_checks'] == 4
    assert verified['index_sha256'] == sha(candidate / INDEX)
    html = (candidate / INDEX).read_text()
    assert 'window.__DTX_DEMO_AUTH_DISABLED__ = false;' in html, 'Normal login must remain enabled'
    live = SOURCE / 'build'
    backup = TOOLS / 'before-download-publish'
    backup.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not (backup / 'native-dist.tar.gz').exists():
        with tarfile.open(str(backup / 'native-dist.tar.gz'), 'w:gz') as archive:
            archive.add(str(live), arcname='build')
        (backup / 'native-dist.tar.gz').chmod(0o600)
    paths = [row.split('\t', 2)[2] for row in run(['git', 'apply', '--numstat', PATCH]).splitlines()]
    assert all(not Path(p).is_absolute() and '..' not in Path(p).parts for p in paths)
    if not (backup / 'native-source.tar.gz').exists():
        with tarfile.open(str(backup / 'native-source.tar.gz'), 'w:gz') as archive:
            for rel in paths:
                if (SOURCE / rel).is_file():
                    archive.add(str(SOURCE / rel), arcname=rel)
        (backup / 'native-source.tar.gz').chmod(0o600)
    old_hashed = {str(p.relative_to(live)): sha(p) for p in live.rglob('*')
                  if p.is_file() and re.search(r'[.\-][0-9a-f]{8,}[.\-]', p.name)}
    apply_patch(SOURCE)
    run(['rsync', '-a', '--exclude=/' + str(INDEX), str(candidate) + '/', str(live) + '/'])
    assert all((live / rel).is_file() and sha(live / rel) == digest
               for rel, digest in old_hashed.items()), 'Old hashed resources must remain available'
    target = live / INDEX
    temporary = target.with_name(target.name + '.download-recovery')
    shutil.copy2(str(candidate / INDEX), str(temporary))
    os.replace(str(temporary), str(target))
    record = {'patch_sha256': sha(PATCH), 'index_sha256': sha(target),
              'old_hashed_assets_retained': len(old_hashed), 'verified_build': verified,
              'dist_backup': str(backup / 'native-dist.tar.gz'),
              'source_backup': str(backup / 'native-source.tar.gz'),
              'source_files': paths, 'backend_or_database_changed': False}
    (TOOLS / 'native-download-release.json').write_text(json.dumps(record, indent=2))
    print(json.dumps(record))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish-built', action='store_true',
                        help='publish the already built candidate bound to verified-build.json')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise RuntimeError('Run on the office server as root')
    TOOLS.mkdir(mode=0o700, parents=True, exist_ok=True)
    TOOLS.chmod(0o700)
    if not args.publish_built:
        build()
    publish()


if __name__ == '__main__':
    main()
