#!/usr/bin/env python3
"""Export an offline release without databases, identities or training outputs."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile

SOURCE = Path(os.environ.get('PPCI_SOURCE_ROOT', '/opt/ppci-source'))
BUILD = Path(os.environ.get('PPCI_BUILD_ROOT', '/opt/ppci-build'))
IMAGES = ['ppci/kuscia:home-20260912', 'secretflow/fate2-adapter:0.2.0-native',
          'federatedai/standalone_fate:2.2.0',
          'secretflow-registry.cn-hangzhou.cr.aliyuncs.com/secretflow/secretflow-lite-anolis8:1.11.0b1',
          'registry.baidubce.com/paddledtx/xchain:v3.9',
          'registry.baidubce.com/paddledtx/xdb-dataowner:2.1',
          'registry.baidubce.com/paddledtx/xdb-storage:2.1',
          'registry.baidubce.com/paddledtx/paddledtx-dai:2.1',
          'registry.baidubce.com/paddledtx/paddledtx-visual:1.0',
          'ppci/bfia-cpp:home-20260912', 'ppci/bfia-python:amd64-20260908']
IMAGES += [f'secretflow-registry.cn-hangzhou.cr.aliyuncs.com/secretflow/{name}:latest'
           for name in ('ecdh', 'ecdh-psi', 'ss-compare', 'ss-lr', 'ss-pearson', 'ss-vif', 'ss-xgb')]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=Path('/home/ppci/releases'))
    p.add_argument('--with-images', action='store_true')
    a = p.parse_args()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S')
    dest = a.output / stamp
    dest.mkdir(parents=True)
    files = [(BUILD / 'secretpad/target/secretpad.jar', 'secretpad/target/secretpad.jar'),
             (BUILD / 'secretpad-kimi-upstream/target/secretpad.jar', 'secretpad-kimi-upstream/target/secretpad.jar'),
             (BUILD / 'secretpad-frontend/apps/platform/dist', 'secretpad-frontend/apps/platform/dist'),
             (BUILD / 'paddle/paddlempc', 'paddle/paddlempc'),
             (BUILD / 'paddle/requester-cli-current', 'paddle/requester-cli-current'),
             (SOURCE / 'NewProject/scripts', 'scripts')]
    for path, _ in files:
        if not path.exists(): raise FileNotFoundError(path)
    with tarfile.open(dest / 'artifacts.tar.gz', 'w:gz') as archive:
        for path, name in files:
            archive.add(path, arcname=name, filter=lambda item: None if '__pycache__' in item.name else item)
    manifest = {'created_utc': stamp, 'platform': 'linux/amd64', 'runtime_data_included': False,
                'source': {}, 'images': [], 'sha256': {}}
    for repo in ['.', 'NewProject/secretpad', 'NewProject/secretpad-kimi-upstream',
                 'NewProject/secretpad-frontend', 'NewProject/kuscia', 'NewProject/secretflow', 'NewProject/yacl',
                 'PaddleDTX']:
        path = SOURCE / repo
        manifest['source'][repo] = {
            'head': subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip(),
            'status': subprocess.check_output(['git', '-C', str(path), 'status', '--short'], text=True)}
    if a.with_images:
        for image in IMAGES:
            info = json.loads(subprocess.check_output(['docker', 'image', 'inspect', image]))[0]
            manifest['images'].append({'tag': image, 'id': info['Id'], 'digests': info.get('RepoDigests', [])})
        with (dest / 'images.tar.gz').open('wb') as out:
            save = subprocess.Popen(['docker', 'save', '--platform=linux/amd64', *IMAGES], stdout=subprocess.PIPE)
            gzip = subprocess.Popen(['gzip', '-1'], stdin=save.stdout, stdout=out)
            save.stdout.close()
            if gzip.wait() or save.wait(): raise RuntimeError('Image export failed')
    for path in dest.iterdir():
        with path.open('rb') as stream:
            manifest['sha256'][path.name] = hashlib.file_digest(stream, 'sha256').hexdigest()
    (dest / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    (dest / 'SHA256SUMS').write_text(''.join(f'{digest}  {name}\n' for name, digest in manifest['sha256'].items()))
    print(dest, flush=True)


if __name__ == '__main__':
    main()
